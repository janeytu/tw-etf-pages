"""Render static HTML site from snapshots + change reports."""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .compare import list_snapshot_dates, load_snapshot
from .config import AppConfig
from .trend import build_holdings_trend
from .taiex_kd import build_kd_view
from .margin_ratio import build_margin_view
from .utils import now_taipei_iso, read_json, write_json

logger = logging.getLogger(__name__)

TEMPLATES = Path(__file__).parent / "templates"
STATIC = Path(__file__).parent / "static"


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["lots"] = format_lots
    env.filters["signed_lots"] = format_signed_lots
    env.filters["weight"] = format_weight
    return env


def format_lots(shares: Any) -> str:
    """Format share count as 張 (1 lot = 1000 shares)."""
    if shares is None:
        return "—"
    lots = int(shares) / 1000.0
    if abs(lots - round(lots)) < 1e-9:
        return f"{int(round(lots)):,} 張"
    s = f"{lots:,.3f}".rstrip("0").rstrip(".")
    return f"{s} 張"


def format_signed_lots(delta: Any) -> str:
    if delta is None:
        return "—"
    lots = int(delta) / 1000.0
    sign = "+" if lots > 0 else ""
    if abs(lots - round(lots)) < 1e-9:
        return f"{sign}{int(round(lots)):,}張"
    return f"{sign}{lots:,.3f}張"


def format_weight(value: Any) -> str:
    if value is None:
        return "—"
    return f"{float(value):.2f}"


def latest_change_report(cfg: AppConfig, ticker: str) -> dict[str, Any] | None:
    d = cfg.changes_dir / ticker
    if not d.is_dir():
        return None
    files = sorted(d.glob("*.json"))
    if not files:
        return None
    return read_json(files[-1])


def latest_snapshot(cfg: AppConfig, ticker: str) -> dict[str, Any] | None:
    dates = list_snapshot_dates(cfg.snapshots_dir, ticker)
    if not dates:
        return None
    return load_snapshot(cfg.snapshots_dir, ticker, dates[-1])


def list_change_dates(changes_dir: Path, ticker: str) -> list[date]:
    """Return archived change-report dates ascending."""
    d = changes_dir / ticker
    if not d.is_dir():
        return []
    dates: list[date] = []
    for p in d.glob("*.json"):
        try:
            dates.append(date.fromisoformat(p.stem))
        except ValueError:
            continue
    return sorted(dates)


def load_change_report(changes_dir: Path, ticker: str, as_of: date) -> dict[str, Any]:
    return read_json(changes_dir / ticker / f"{as_of.isoformat()}.json")


def ensure_change_reports(cfg: AppConfig, ticker: str) -> int:
    """
    Fill missing data/changes/{ticker}/{date}.json by comparing consecutive
    archived snapshots. Existing reports are left untouched. Returns count written.
    """
    from .compare import compare_snapshots, save_change_report

    dates = list_snapshot_dates(cfg.snapshots_dir, ticker)
    if len(dates) < 2:
        return 0
    written = 0
    for i in range(1, len(dates)):
        prev_d, curr_d = dates[i - 1], dates[i]
        out = cfg.changes_dir / ticker / f"{curr_d.isoformat()}.json"
        if out.is_file():
            continue
        prev = load_snapshot(cfg.snapshots_dir, ticker, prev_d)
        curr = load_snapshot(cfg.snapshots_dir, ticker, curr_d)
        report = compare_snapshots(prev, curr, cfg)
        save_change_report(cfg, report)
        written += 1
        logger.info("Backfilled change report %s %s vs %s", ticker, curr_d, prev_d)
    return written


# Max dates shown in the 「異動資料日」 selector (newest first).
CHANGE_HISTORY_MAX_DAYS = 10


def build_change_history(
    cfg: AppConfig,
    ticker: str,
    *,
    max_days: int = CHANGE_HISTORY_MAX_DAYS,
) -> list[dict[str, Any]]:
    """
    Load recent change reports under data/changes/{ticker}/ (newest first).

    Only the latest ``max_days`` (default 10) dates appear in the date menu;
    older archives stay on GitHub under data/changes/ but are not listed in UI.
    Each entry includes pre-built table rows for client-side date switching.
    """
    dates = list_change_dates(cfg.changes_dir, ticker)
    if max_days > 0:
        dates = dates[-max_days:]
    history: list[dict[str, Any]] = []
    for as_of in reversed(dates):  # newest first
        report = load_change_report(cfg.changes_dir, ticker, as_of)
        snap_path = cfg.snapshots_dir / ticker / f"{as_of.isoformat()}.json"
        snap = load_snapshot(cfg.snapshots_dir, ticker, as_of) if snap_path.is_file() else None
        rows = build_etf_table_rows(report, snap)
        summary = report.get(
            "summary",
            {"first_buy": 0, "increase": 0, "decrease": 0, "full_exit": 0},
        )
        history.append(
            {
                "as_of_date": report.get("as_of_date") or as_of.isoformat(),
                "prev_as_of_date": report.get("prev_as_of_date"),
                "source": report.get("source"),
                "summary": summary,
                "changed_count": sum(1 for r in rows if r["changed"]),
                "rows": rows,
                "first_buy": report.get("first_buy", []),
                "increase": report.get("increase", []),
                "decrease": report.get("decrease", []),
                "full_exit": report.get("full_exit", []),
            }
        )
    return history


def _status_for_change(kind: str, streak: int, shares_delta: int) -> dict[str, str]:
    """Build display status label + CSS class (no fabricated 億 amounts)."""
    streak = max(int(streak or 1), 1)
    delta_txt = format_signed_lots(shares_delta)
    if kind == "first_buy":
        return {
            "kind": kind,
            "css": "status-buy",
            "label": f"新建倉 ({delta_txt})",
            "short": "新建倉",
        }
    if kind == "increase":
        return {
            "kind": kind,
            "css": "status-inc",
            "label": f"加碼(連{streak}天 / {delta_txt})",
            "short": f"加碼(連{streak}天)",
            "streak_text": f"連{streak}買",
        }
    if kind == "decrease":
        return {
            "kind": kind,
            "css": "status-dec",
            "label": f"減碼(連{streak}天 / {delta_txt})",
            "short": f"減碼(連{streak}天)",
            "streak_text": f"連{streak}賣",
        }
    if kind == "full_exit":
        return {
            "kind": kind,
            "css": "status-exit",
            "label": f"全部出清 ({delta_txt})",
            "short": "全部出清",
            "streak_text": "全部出清",
        }
    return {"kind": "flat", "css": "status-flat", "label": "持平", "short": "持平"}


def _change_index(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not report:
        return out
    for kind in ("first_buy", "increase", "decrease", "full_exit"):
        for row in report.get(kind, []):
            code = row["stock_code"]
            status = _status_for_change(kind, row.get("streak_days", 1), row.get("shares_delta", 0))
            out[code] = {
                **row,
                "change_kind": kind,
                "status": status,
                "changed": True,
            }
    return out


def build_etf_table_rows(
    report: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Rows for per-ETF table: changed holdings first, then unchanged (excl. placeholders).
    Full-exit names come from the change report (no longer in snapshot).
    """
    changed = _change_index(report)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Prefer changed order: first_buy, increase, decrease, full_exit (already in report)
    if report:
        for kind in ("first_buy", "increase", "decrease", "full_exit"):
            for row in report.get(kind, []):
                code = row["stock_code"]
                seen.add(code)
                prev_w = row.get("prev_weight_pct")
                curr_w = row.get("curr_weight_pct")
                w_delta = None
                if prev_w is not None and curr_w is not None:
                    w_delta = float(curr_w) - float(prev_w)
                rows.append(
                    {
                        "stock_code": code,
                        "stock_name": row.get("stock_name") or "",
                        "curr_shares": row.get("curr_shares", 0),
                        "prev_shares": row.get("prev_shares", 0),
                        "shares_delta": row.get("shares_delta", 0),
                        "curr_weight_pct": curr_w,
                        "prev_weight_pct": prev_w,
                        "weight_delta": w_delta,
                        "changed": True,
                        "change_kind": kind,
                        "status": changed[code]["status"],
                    }
                )

    if snapshot:
        for h in snapshot.get("holdings", []):
            if h.get("is_placeholder"):
                continue
            code = h["stock_code"]
            if code in seen:
                continue
            seen.add(code)
            rows.append(
                {
                    "stock_code": code,
                    "stock_name": h.get("stock_name") or "",
                    "curr_shares": h.get("shares", 0),
                    "prev_shares": h.get("shares", 0),
                    "shares_delta": 0,
                    "curr_weight_pct": h.get("weight_pct"),
                    "prev_weight_pct": h.get("weight_pct"),
                    "weight_delta": 0.0,
                    "changed": False,
                    "change_kind": "flat",
                    "status": _status_for_change("flat", 1, 0),
                }
            )

    return rows


def build_cross_add_remove(
    etf_blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    adds: list[dict[str, Any]] = []
    rems: list[dict[str, Any]] = []
    for block in etf_blocks:
        report = block.get("report")
        if not report:
            continue
        ticker = block["ticker"]
        name = block["name"]
        for row in report.get("first_buy", []):
            adds.append(
                {
                    "ticker": ticker,
                    "etf_name": name,
                    "stock_code": row["stock_code"],
                    "stock_name": row.get("stock_name") or "",
                    "shares_delta": row.get("shares_delta", 0),
                    "as_of_date": report.get("as_of_date"),
                }
            )
        for row in report.get("full_exit", []):
            rems.append(
                {
                    "ticker": ticker,
                    "etf_name": name,
                    "stock_code": row["stock_code"],
                    "stock_name": row.get("stock_name") or "",
                    "shares_delta": row.get("shares_delta", 0),
                    "as_of_date": report.get("as_of_date"),
                }
            )
    adds.sort(key=lambda r: (r["ticker"], r["stock_code"]))
    rems.sort(key=lambda r: (r["ticker"], r["stock_code"]))
    return adds, rems


def build_water_levels(
    etf_blocks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Aggregate per-stock net share change across watchlist ETFs."""
    by_code: dict[str, dict[str, Any]] = {}

    for block in etf_blocks:
        report = block.get("report")
        if not report:
            continue
        ticker = block["ticker"]
        etf_name = block["name"]
        for kind in ("first_buy", "increase", "decrease", "full_exit"):
            for row in report.get(kind, []):
                code = row["stock_code"]
                entry = by_code.setdefault(
                    code,
                    {
                        "stock_code": code,
                        "stock_name": row.get("stock_name") or "",
                        "net_delta": 0,
                        "details": [],
                    },
                )
                if not entry["stock_name"] and row.get("stock_name"):
                    entry["stock_name"] = row["stock_name"]
                delta = int(row.get("shares_delta") or 0)
                entry["net_delta"] += delta
                status = _status_for_change(kind, row.get("streak_days", 1), delta)
                streak_bit = status.get("streak_text") or status["short"]
                detail_css = {
                    "first_buy": "buy",
                    "increase": "buy",
                    "decrease": "sell",
                    "full_exit": "exit",
                }[kind]
                entry["details"].append(
                    {
                        "ticker": ticker,
                        "etf_name": etf_name,
                        "kind": kind,
                        "css": detail_css,
                        "text": f"{ticker} {etf_name} ({streak_bit} / {format_signed_lots(delta)})",
                        "shares_delta": delta,
                    }
                )

    increases: list[dict[str, Any]] = []
    decreases: list[dict[str, Any]] = []
    for entry in by_code.values():
        entry["details"].sort(key=lambda d: (-abs(d["shares_delta"]), d["ticker"]))
        if entry["net_delta"] > 0:
            increases.append(entry)
        elif entry["net_delta"] < 0:
            decreases.append(entry)
        else:
            # Mixed to net zero — still useful; put under decrease side as 「淨持平」
            # Prefer showing in increases if any buy activity, else decreases.
            if any(d["kind"] in ("first_buy", "increase") for d in entry["details"]):
                increases.append(entry)
            else:
                decreases.append(entry)

    increases.sort(key=lambda e: (-abs(e["net_delta"]), e["stock_code"]))
    decreases.sort(key=lambda e: (-abs(e["net_delta"]), e["stock_code"]))
    return increases, decreases


def _copy_static(site: Path) -> None:
    dest = site / "assets"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("style.css", "app.js"):
        src = STATIC / name
        if src.is_file():
            shutil.copy2(src, dest / name)


def render_site(cfg: AppConfig) -> Path:
    env = _env()
    site = cfg.site_dir
    site.mkdir(parents=True, exist_ok=True)
    generated_at = now_taipei_iso()
    _copy_static(site)

    all_etfs_meta = [{"ticker": e.ticker, "name": e.name} for e in cfg.etfs]
    etf_blocks: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []

    # Ensure consecutive snapshot pairs have change JSON (fills gaps e.g. FH backfill)
    data_out = site / "data"
    data_out.mkdir(parents=True, exist_ok=True)

    for etf in cfg.etfs:
        n_backfill = ensure_change_reports(cfg, etf.ticker)
        if n_backfill:
            logger.info("%s: backfilled %d change report(s)", etf.ticker, n_backfill)

        snap = latest_snapshot(cfg, etf.ticker)
        change_history = build_change_history(cfg, etf.ticker)
        report = None
        if change_history:
            latest_d = date.fromisoformat(change_history[0]["as_of_date"])
            report = load_change_report(cfg.changes_dir, etf.ticker, latest_d)
        summary = {"first_buy": 0, "increase": 0, "decrease": 0, "full_exit": 0}
        if report:
            summary = report.get("summary", summary)
        rows = (
            change_history[0]["rows"]
            if change_history
            else build_etf_table_rows(report, snap)
        )
        changed_count = (
            change_history[0]["changed_count"]
            if change_history
            else sum(1 for r in rows if r["changed"])
        )
        available_dates = [h["as_of_date"] for h in change_history]
        trend = build_holdings_trend(
            cfg.snapshots_dir, etf.ticker, cfg.placeholder
        )
        block = {
            "ticker": etf.ticker,
            "name": etf.name,
            "anchor": f"act_{etf.ticker}",
            "as_of_date": (report or snap or {}).get("as_of_date"),
            "prev_as_of_date": (report or {}).get("prev_as_of_date"),
            "source": (report or snap or {}).get("source"),
            "source_page": etf.source_page,
            "summary": summary,
            "report": report,
            "snapshot": snap,
            "rows": rows,
            "changed_count": changed_count,
            "holdings_count": (snap or {}).get("holdings_count"),
            "trend": trend,
            "change_history": change_history,
            "available_dates": available_dates,
        }
        etf_blocks.append(block)
        index_rows.append(
            {
                "ticker": etf.ticker,
                "name": etf.name,
                "as_of_date": block["as_of_date"],
                "prev_as_of_date": block["prev_as_of_date"],
                "source": block["source"],
                "summary": summary,
                "available_dates": available_dates,
            }
        )

        # JSON asset for Pages date menu / external reuse
        write_json(
            data_out / f"{etf.ticker}-changes.json",
            {
                "etf_ticker": etf.ticker,
                "dates": available_dates,
                "history": change_history,
            },
        )

        html = env.get_template("etf.html").render(
            ticker=etf.ticker,
            name=etf.name,
            anchor=block["anchor"],
            as_of_date=block["as_of_date"],
            prev_as_of_date=block["prev_as_of_date"],
            source=block["source"],
            source_page=etf.source_page,
            report=report,
            snapshot=snap,
            rows=rows,
            changed_count=changed_count,
            summary=summary,
            trend=trend,
            change_history=change_history,
            available_dates=available_dates,
            all_etfs=all_etfs_meta,
            generated_at=generated_at,
            ph_max_shares=cfg.placeholder.max_shares,
            ph_max_weight=cfg.placeholder.max_weight_pct,
            assets_prefix="assets",
            issuer=etf.issuer,
        )
        (site / f"{etf.ticker}.html").write_text(html, encoding="utf-8")
        logger.info("Wrote %s", site / f"{etf.ticker}.html")

    adds, rems = build_cross_add_remove(etf_blocks)
    water_inc, water_dec = build_water_levels(etf_blocks)

    as_of_dates = sorted({b["as_of_date"] for b in etf_blocks if b.get("as_of_date")})
    report_date_label = "／".join(as_of_dates) if as_of_dates else "—"
    totals = {
        "first_buy": sum(b["summary"]["first_buy"] for b in etf_blocks),
        "increase": sum(b["summary"]["increase"] for b in etf_blocks),
        "decrease": sum(b["summary"]["decrease"] for b in etf_blocks),
        "full_exit": sum(b["summary"]["full_exit"] for b in etf_blocks),
    }

    kd = None
    try:
        kd = build_kd_view(cfg.root)
    except Exception:  # noqa: BLE001 — never break the site for KD
        logger.exception("TAIEX KD view failed")
    import json as _json

    mg = None
    try:
        mg = build_margin_view(cfg.root)
        if mg:
            closes = {}
            kd_file = cfg.root / "data" / "taiex" / "kd.json"
            if kd_file.is_file():
                closes = {r["date"]: r["close"] for r in read_json(kd_file).get("rows", [])}
            for r in mg["full"] + mg["chart"] + [mg["latest"]]:
                r["taiex"] = closes.get(r["date"])
            mg["chart_json"] = _json.dumps(
                [{"date": r["date"], "ratio": r["ratio"], "taiex": r.get("taiex")} for r in mg["chart"]],
                ensure_ascii=False,
            ).replace("</", "<\\/")
    except Exception:  # noqa: BLE001 — never break the site for margin
        logger.exception("Margin ratio view failed")
        mg = None
    if kd or mg:
        if kd:
            kd["chart_json"] = _json.dumps(
                [{"date": r["date"], "close": r["close"], "k": r["k"], "d": r["d"]} for r in kd["chart"]],
                ensure_ascii=False,
            ).replace("</", "<\\/")
        (site / "taiex-kd.html").write_text(
            env.get_template("taiex_kd.html").render(
                kd=kd, mg=mg, generated_at=generated_at, assets_prefix="assets"
            ),
            encoding="utf-8",
        )
        logger.info("Wrote %s", site / "taiex-kd.html")

    index_html = env.get_template("index.html").render(
        kd=kd,
        mg=mg,
        etfs=index_rows,
        etf_blocks=etf_blocks,
        cross_adds=adds,
        cross_rems=rems,
        water_inc=water_inc,
        water_dec=water_dec,
        report_date_label=report_date_label,
        totals=totals,
        generated_at=generated_at,
        assets_prefix="assets",
    )
    (site / "index.html").write_text(index_html, encoding="utf-8")

    (site / ".nojekyll").write_text("", encoding="utf-8")
    logger.info("Wrote %s", site / "index.html")
    return site
