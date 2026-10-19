"""End-to-end pipeline: fetch → parse → archive → compare → render."""

from __future__ import annotations

import logging
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .compare import (
    compare_snapshots,
    previous_snapshot_date,
    save_change_report,
    save_snapshot,
)
from .config import AppConfig, EtfConfig, load_config
from .fetch import FetchError, fetch_etf_holdings
from .parse import parse_excel_for_issuer, parse_uni_excel, parse_fh_excel, parse_zdsetf_snapshot, parse_yuanta_ratio, parse_cathay_weights, parse_uobam_pcf, parse_capital_buyback, parse_kgi_holdings
from .render import render_site
from .utils import read_json, write_json

logger = logging.getLogger(__name__)


def _parse_fetched(
    cfg: AppConfig, etf: EtfConfig, path: Path, kind: str
) -> dict[str, Any]:
    if kind == "uni_excel":
        return parse_uni_excel(path, etf.ticker, cfg.placeholder)
    if kind == "fh_excel":
        return parse_fh_excel(path, etf.ticker, cfg.placeholder)
    if kind == "zdsetf":
        return parse_zdsetf_snapshot(path, etf.ticker, cfg.placeholder)
    if kind == "yuanta":
        return parse_yuanta_ratio(path, etf.ticker, cfg.placeholder)
    if kind == "cathay":
        return parse_cathay_weights(path, etf.ticker, cfg.placeholder)
    if kind == "uobam":
        return parse_uobam_pcf(path, etf.ticker, cfg.placeholder)
    if kind == "capital":
        return parse_capital_buyback(path, etf.ticker, cfg.placeholder)
    if kind == "kgi":
        return parse_kgi_holdings(path, etf.ticker, cfg.placeholder)
    raise ValueError(kind)


def process_etf(
    cfg: AppConfig,
    etf: EtfConfig,
    *,
    offline: bool = False,
    allow_fallback: bool = True,
) -> dict[str, Any]:
    """Fetch (unless offline sample already archived), compare, return status."""
    if offline:
        raise RuntimeError("process_etf offline path should use dry_run helpers")

    path, kind = fetch_etf_holdings(cfg, etf, allow_fallback=allow_fallback)
    snapshot = _parse_fetched(cfg, etf, path, kind)
    snap_path = save_snapshot(cfg, snapshot)
    logger.info("Archived snapshot %s", snap_path)

    as_of = date.fromisoformat(snapshot["as_of_date"])
    prev_d = previous_snapshot_date(cfg.snapshots_dir, etf.ticker, as_of)
    report = None
    if prev_d is None:
        logger.info("%s: no previous snapshot before %s — skip compare", etf.ticker, as_of)
    else:
        prev = read_json(cfg.snapshots_dir / etf.ticker / f"{prev_d.isoformat()}.json")
        report = compare_snapshots(prev, snapshot, cfg)
        save_change_report(cfg, report)
        logger.info(
            "%s changes vs %s: %s",
            etf.ticker,
            prev_d,
            report["summary"],
        )
    return {"ticker": etf.ticker, "snapshot": snapshot, "report": report}


def _sample_map(samples: Path) -> dict[str, list[Path]]:
    """Map ticker → sample excel paths (sorted by name / date)."""
    mapping: dict[str, list[Path]] = {
        "00981A": [samples / "00981A_ETF_Investment_Portfolio_20260922.xlsx"],
        "00988A": [samples / "00988A_ETF_Investment_Portfolio_20260921.xlsx"],
        "00403A": [samples / "00403A_ETF_Investment_Portfolio_20260922.xlsx"],
        "00991A": [
            samples / "00991A_20260918.xlsx",
            samples / "00991A_20260922.xlsx",
        ],
        "00929": [samples / "00929_20260924.xlsx"],
        "00939": [samples / "00939_20260924.xlsx"],
    }
    return mapping


def _synthesize_prev_from_changes(
    curr: dict[str, Any],
    changes_path: Path,
    cfg: AppConfig,
) -> dict[str, Any]:
    """
    Build a synthetic previous-day snapshot by reversing zdsetf change deltas.
    Used for Uni dry-run when only one official Excel sample exists.
    """
    changes = read_json(changes_path)
    if not isinstance(changes, list):
        changes = changes.get("changes", [])
    by_code = {h["stock_code"]: dict(h) for h in curr["holdings"]}

    for ch in changes:
        code = str(ch["stock_code"]).strip().upper()
        ctype = ch.get("change_type", "")
        raw_prev = ch.get("prev_shares")
        prev_shares = int(raw_prev) if raw_prev is not None else 0
        name = ch.get("stock_name") or by_code.get(code, {}).get("stock_name", "")
        prev_w = ch.get("prev_weight")
        try:
            prev_w_f = float(prev_w) if prev_w is not None else 0.0
        except (TypeError, ValueError):
            prev_w_f = 0.0

        if ctype == "NEW":
            by_code.pop(code, None)
        elif ctype == "REMOVED":
            by_code[code] = {
                "stock_code": code,
                "stock_name": name,
                "shares": prev_shares,
                "weight_pct": prev_w_f,
                "is_placeholder": (
                    prev_shares <= cfg.placeholder.max_shares
                    and prev_w_f < cfg.placeholder.max_weight_pct
                ),
            }
        else:
            # INCREASE / DECREASE: restore prev shares
            if code in by_code:
                by_code[code]["shares"] = prev_shares
                if prev_w is not None:
                    by_code[code]["weight_pct"] = prev_w_f
                by_code[code]["is_placeholder"] = (
                    prev_shares <= cfg.placeholder.max_shares
                    and float(by_code[code].get("weight_pct") or 0)
                    < cfg.placeholder.max_weight_pct
                )
            else:
                by_code[code] = {
                    "stock_code": code,
                    "stock_name": name,
                    "shares": prev_shares,
                    "weight_pct": prev_w_f,
                    "is_placeholder": False,
                }

    as_of = date.fromisoformat(curr["as_of_date"])
    prev_as_of = as_of - timedelta(days=1)
    # skip weekend-ish: just use calendar -1 for synthetic
    holdings = list(by_code.values())
    return {
        "etf_ticker": curr["etf_ticker"],
        "as_of_date": prev_as_of.isoformat(),
        "source": "synthetic_from_zdsetf_changes",
        "fetched_at": curr.get("fetched_at"),
        "raw_file": changes_path.name,
        "raw_file_hash": "synthetic",
        "holdings_count": len(holdings),
        "placeholder_count": sum(1 for h in holdings if h.get("is_placeholder")),
        "meta": {"note": "dry-run previous snapshot synthesized from zdsetf changes"},
        "holdings": holdings,
    }


def dry_run(cfg: AppConfig | None = None) -> Path:
    """
    Offline pipeline using samples/ Excels (and zdsetf changes to synthesize
    prior day for Uni tickers that only have one sample date).
    """
    cfg = cfg or load_config()
    # clean prior dry-run artifacts for determinism? keep additive — overwrite same dates
    samples = cfg.samples_dir
    sample_files = _sample_map(samples)

    for etf in cfg.etfs:
        paths = [p for p in sample_files.get(etf.ticker, []) if p.is_file()]
        if not paths:
            logger.warning("No sample for %s — skip", etf.ticker)
            continue

        snapshots: list[dict[str, Any]] = []
        for p in paths:
            # copy into raw for traceability
            dest = cfg.raw_dir / etf.ticker / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            snap = parse_excel_for_issuer(dest, etf.ticker, etf.issuer, cfg)
            save_snapshot(cfg, snap)
            snapshots.append(snap)
            logger.info("Dry-run parsed %s → %s", p.name, snap["as_of_date"])

        # Uni / single-date: synthesize previous from zdsetf changes
        if len(snapshots) == 1:
            ch_path = samples / f"zdsetf_{etf.ticker}_changes.json"
            if ch_path.is_file():
                prev = _synthesize_prev_from_changes(snapshots[0], ch_path, cfg)
                save_snapshot(cfg, prev)
                snapshots.insert(0, prev)
                logger.info(
                    "Synthesized prev %s for %s", prev["as_of_date"], etf.ticker
                )

        # Compare consecutive archived dates for this ticker
        from .compare import list_snapshot_dates

        dates = list_snapshot_dates(cfg.snapshots_dir, etf.ticker)
        if len(dates) >= 2:
            prev_d, curr_d = dates[-2], dates[-1]
            prev = read_json(cfg.snapshots_dir / etf.ticker / f"{prev_d.isoformat()}.json")
            curr = read_json(cfg.snapshots_dir / etf.ticker / f"{curr_d.isoformat()}.json")
            report = compare_snapshots(prev, curr, cfg)
            save_change_report(cfg, report)
            logger.info("%s dry-run changes: %s", etf.ticker, report["summary"])

    site = render_site(cfg)
    # marker
    from .utils import now_taipei_iso

    write_json(
        cfg.root / "data" / "last_run.json",
        {"mode": "dry-run", "generated_at": now_taipei_iso()},
    )
    return site


def run_live(cfg: AppConfig | None = None, *, allow_fallback: bool = True) -> Path:
    cfg = cfg or load_config()
    errors: list[str] = []
    for etf in cfg.etfs:
        try:
            process_etf(cfg, etf, allow_fallback=allow_fallback)
        except Exception as exc:  # noqa: BLE001 — collect per-etf failures
            logger.exception("Failed processing %s", etf.ticker)
            errors.append(f"{etf.ticker}: {exc}")
    try:
        from .taiex_kd import update_kd

        update_kd(cfg.root)
    except Exception:  # noqa: BLE001 — KD must never fail the run
        logger.exception("TAIEX KD update failed")
    try:
        from .margin_ratio import update_margin

        update_margin(cfg.root)
    except Exception:  # noqa: BLE001 — margin ratio must never fail the run
        logger.exception("Margin ratio update failed")
    site = render_site(cfg)
    from .utils import now_taipei_iso

    write_json(
        cfg.root / "data" / "last_run.json",
        {
            "mode": "live",
            "generated_at": now_taipei_iso(),
            "errors": errors,
        },
    )
    if errors:
        logger.error("Completed with errors: %s", errors)
    return site
