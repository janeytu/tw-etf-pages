"""TAIEX (發行量加權股價指數) daily KD(9,3,3) indicator.

Source: TWSE MI_5MINS_HIST (monthly daily OHLC of the weighted index).
History is stored in data/taiex/kd.json and accumulates; KD is recomputed
from the earliest stored day (seed K=D=50) on every update so values are
deterministic. Network failures never raise — stored history is reused.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path
from typing import Any

import requests

from .utils import now_taipei_iso, read_json, write_json

logger = logging.getLogger(__name__)

TWSE_URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST"
SOURCE_PAGE = "https://www.twse.com.tw/zh/indices/taiex/mi-5min-hist.html"
PERIOD = 9
OVERSOLD = 20.0
OVERBOUGHT = 80.0
WARMUP_MONTHS = 8  # first build: ~170 trading days of warm-up
UA = "Mozilla/5.0 (compatible; tw-etf-pages/1.0; +https://solymx.github.io/tw-etf-pages/)"


def kd_path(root: Path) -> Path:
    return root / "data" / "taiex" / "kd.json"


def _num(s: Any) -> float:
    return float(str(s).replace(",", "").strip())


def _roc_to_iso(s: str) -> str:
    y, m, d = (int(x) for x in str(s).strip().split("/"))
    return date(y + 1911, m, d).isoformat()


def _month_starts(today: date, n: int) -> list[date]:
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return sorted(out)


def fetch_month(session: requests.Session, month: date) -> list[dict[str, Any]]:
    params = {"date": month.strftime("%Y%m01"), "response": "json"}
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            try:
                r = session.get(TWSE_URL, params=params, timeout=20)
            except requests.exceptions.SSLError:
                r = session.get(TWSE_URL, params=params, timeout=20, verify=False)
            r.raise_for_status()
            js = r.json()
            if js.get("stat") != "OK":
                # e.g. "很抱歉，沒有符合條件的資料!" for a month with no trading yet
                logger.info("TWSE %s: %s", params["date"], js.get("stat"))
                return []
            rows = []
            for row in js.get("data") or []:
                try:
                    rows.append(
                        {
                            "date": _roc_to_iso(row[0]),
                            "open": _num(row[1]),
                            "high": _num(row[2]),
                            "low": _num(row[3]),
                            "close": _num(row[4]),
                        }
                    )
                except (ValueError, IndexError) as exc:
                    logger.warning("skip bad TAIEX row %s: %s", row, exc)
            return rows
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"TWSE fetch {params['date']} failed: {last_exc}")


def compute_kd(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """rows sorted by date with high/low/close; adds rsv/k/d (rounded 2dp)."""
    k_prev = d_prev = 50.0
    out = []
    for i, r in enumerate(rows):
        win = rows[max(0, i - PERIOD + 1) : i + 1]
        hi = max(x["high"] for x in win)
        lo = min(x["low"] for x in win)
        rsv = 50.0 if hi == lo else (r["close"] - lo) / (hi - lo) * 100.0
        k = k_prev * 2 / 3 + rsv / 3
        d = d_prev * 2 / 3 + k / 3
        k_prev, d_prev = k, d
        out.append({**r, "rsv": round(rsv, 2), "k": round(k, 2), "d": round(d, 2)})
    return out


def update_kd(root: Path, today: date | None = None) -> dict[str, Any] | None:
    """Fetch recent months, merge into stored history, recompute. Never raises."""
    path = kd_path(root)
    stored = read_json(path) if path.is_file() else {}
    by_date = {
        r["date"]: {k: r[k] for k in ("date", "open", "high", "low", "close")}
        for r in stored.get("rows", [])
    }
    today = today or date.today()
    n_months = 2 if len(by_date) >= 60 else WARMUP_MONTHS
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    fetched = 0
    errors = []
    for i, m in enumerate(_month_starts(today, n_months)):
        if i:
            time.sleep(1.5)  # TWSE rate limit friendliness
        try:
            for r in fetch_month(session, m):
                by_date[r["date"]] = r
                fetched += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("TAIEX KD: %s", exc)
            errors.append(str(exc))
    if not by_date:
        logger.warning("TAIEX KD: no data available (errors=%s)", errors)
        return stored or None
    rows = compute_kd(sorted(by_date.values(), key=lambda r: r["date"]))
    data = {
        "index": "發行量加權股價指數 (TAIEX)",
        "params": {"period": PERIOD, "k_smooth": 3, "d_smooth": 3, "seed": 50},
        "source": TWSE_URL,
        "updated_at": now_taipei_iso(),
        "fetch_errors": errors,
        "rows": rows,
    }
    write_json(path, data)
    logger.info(
        "TAIEX KD: %d rows (fetched %d), latest %s K=%.2f D=%.2f",
        len(rows), fetched, rows[-1]["date"], rows[-1]["k"], rows[-1]["d"],
    )
    return data


def _zone(v: float) -> str:
    if v < OVERSOLD:
        return "oversold"
    if v > OVERBOUGHT:
        return "overbought"
    return "neutral"


def build_kd_view(root: Path, recent: int = 10, full: int = 60) -> dict[str, Any] | None:
    path = kd_path(root)
    if not path.is_file():
        return None
    data = read_json(path)
    rows = data.get("rows") or []
    # Hide the first ~2 months (warm-up) from display.
    shown = rows[40:] if len(rows) > 80 else rows
    if not shown:
        return None
    view_rows = []
    prev_close = None
    for i, r in enumerate(shown):
        zk, zd = _zone(r["k"]), _zone(r["d"])
        signal = "oversold" if "oversold" in (zk, zd) else (
            "overbought" if "overbought" in (zk, zd) else "neutral"
        )
        idx = rows.index(r)
        prev = rows[idx - 1] if idx > 0 else None
        cross = ""
        if prev:
            if prev["k"] <= prev["d"] and r["k"] > r["d"]:
                cross = "黃金交叉"
            elif prev["k"] >= prev["d"] and r["k"] < r["d"]:
                cross = "死亡交叉"
        chg = r["close"] - prev["close"] if prev else None
        view_rows.append(
            {**r, "k_zone": zk, "d_zone": zd, "signal": signal,
             "cross": cross, "change": chg,
             "change_pct": (chg / prev["close"] * 100) if prev else None}
        )
    latest = view_rows[-1]
    return {
        "latest": latest,
        "recent": list(reversed(view_rows[-recent:])),
        "full": list(reversed(view_rows[-full:])),
        "chart": view_rows[-full:],
        "updated_at": data.get("updated_at"),
        "source": data.get("source", TWSE_URL),
        "source_page": SOURCE_PAGE,
        "oversold": OVERSOLD,
        "overbought": OVERBOUGHT,
    }
