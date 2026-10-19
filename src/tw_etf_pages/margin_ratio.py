"""大盤融資維持率 (TWSE listed market margin maintenance ratio).

ratio = Σ(各股融資今日餘額(張) × 1000 × 收盤價) ÷ 融資金額(仟元 × 1000) × 100
Sources (official TWSE):
  - MI_MARGN (selectType=ALL): per-stock 融資今日餘額 + market 融資金額
  - MI_INDEX (type=ALLBUT0999): per-stock 收盤價
Stocks with no close that day use the previous trading day's close (else excluded).
Listed market (上市, incl. listed ETFs) only — TPEx/OTC not included.
History lives in data/margin/ratio.json. Never raises.
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

MARGN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
INDEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
SOURCE_PAGE = "https://www.twse.com.tw/zh/trading/margin/mi-margn.html"
UA = "Mozilla/5.0 (compatible; tw-etf-pages/1.0; +https://solymx.github.io/tw-etf-pages/)"
MAX_DAYS_PER_RUN = 6


class NoData(Exception):
    pass


def ratio_path(root: Path) -> Path:
    return root / "data" / "margin" / "ratio.json"


def closes_path(root: Path) -> Path:
    return root / "data" / "margin" / "last_closes.json"


def _num(s: Any) -> float | None:
    t = str(s).replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _get(session: requests.Session, url: str, params: dict) -> dict:
    last: Exception | None = None
    for attempt in range(3):
        try:
            try:
                r = session.get(url, params=params, timeout=30)
            except requests.exceptions.SSLError:
                r = session.get(url, params=params, timeout=30, verify=False)
            r.raise_for_status()
            js = r.json()
            if js.get("stat") != "OK":
                raise NoData(js.get("stat"))
            if str(js.get("date", "")) != params.get("date"):
                # TWSE occasionally serves another day's cached report
                raise RuntimeError(f"date mismatch: got {js.get('date')}")
            return js
        except NoData:
            raise
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(3 + attempt * 4)
    raise RuntimeError(f"{url} {params.get('date')}: {last}")


def compute_day(
    session: requests.Session, d: date, last_closes: dict[str, float]
) -> dict[str, Any]:
    ds = d.strftime("%Y%m%d")
    mm = _get(session, MARGN_URL, {"date": ds, "selectType": "ALL", "response": "json"})
    time.sleep(2)
    mi = _get(session, INDEX_URL, {"date": ds, "type": "ALLBUT0999", "response": "json"})
    tables = mm.get("tables") or []
    summary = next(t for t in tables if (t.get("fields") or [""])[0] == "項目")
    detail = next(t for t in tables if (t.get("fields") or [""])[0] == "代號")
    srow = {r[0]: r for r in summary["data"]}
    amt_row = srow["融資金額(仟元)"]
    lots_row = srow["融資(交易單位)"]
    amount_k = _num(amt_row[5])
    prev_amount_k = _num(amt_row[4])
    today_closes: dict[str, float] = {}
    for t in mi.get("tables") or []:
        if (t.get("fields") or [""])[0] == "證券代號":
            for r in t["data"]:
                c = _num(r[8])
                if c:
                    today_closes[r[0].strip()] = c
            break
    else:
        raise NoData("MI_INDEX 無每日收盤行情")
    # No trade today → previous trading day's close only (no stale prices
    # from long-halted stocks). Same convention as istock.tw.
    prev_closes = dict(last_closes)
    last_closes.clear()
    last_closes.update(today_closes)
    closes = {**prev_closes, **today_closes}
    mv = 0.0
    missing = 0
    for r in detail["data"]:
        bal = _num(r[6]) or 0
        if not bal:
            continue
        c = closes.get(r[0].strip())
        if c is None:
            missing += 1
            continue
        mv += bal * 1000 * c
    if not amount_k:
        raise NoData("融資金額為 0")
    return {
        "date": d.isoformat(),
        "ratio": round(mv / (amount_k * 1000) * 100, 2),
        "margin_value_100m": round(mv / 1e8, 2),
        "balance_100m": round(amount_k / 1e5, 2),
        "balance_change_100m": round((amount_k - (prev_amount_k or amount_k)) / 1e5, 2),
        "balance_lots": int(_num(lots_row[5]) or 0),
        "balance_lots_change": int((_num(lots_row[5]) or 0) - (_num(lots_row[4]) or 0)),
        "missing_close": missing,
    }


def _trading_dates(root: Path) -> list[date]:
    p = root / "data" / "taiex" / "kd.json"
    if not p.is_file():
        return []
    return [date.fromisoformat(r["date"]) for r in read_json(p).get("rows", [])]


def update_margin(
    root: Path, since: date | None = None, max_days: int = MAX_DAYS_PER_RUN
) -> dict[str, Any] | None:
    path = ratio_path(root)
    stored = read_json(path) if path.is_file() else {}
    by_date = {r["date"]: r for r in stored.get("rows", [])}
    cp = closes_path(root)
    last_closes: dict[str, float] = read_json(cp) if cp.is_file() else {}
    tdates = _trading_dates(root)
    today = date.today()
    if by_date:
        last = max(date.fromisoformat(k) for k in by_date)
        todo = [d for d in tdates if d > last]
        # today's margin data is published in the evening; KD may not list it yet
        if today.weekday() < 5 and today > last and today not in todo:
            todo.append(today)
    else:
        start = since or (tdates[-60] if len(tdates) >= 60 else (tdates[0] if tdates else today))
        todo = [d for d in tdates if d >= start] or [today]
    todo = sorted(set(todo))[-max_days:] if by_date else sorted(set(todo))
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json"})
    added = 0
    for d in todo:
        try:
            row = compute_day(session, d, last_closes)
            by_date[row["date"]] = row
            added += 1
            logger.info("Margin ratio %s: %.2f%%", row["date"], row["ratio"])
        except NoData as exc:
            logger.info("Margin ratio %s: no data (%s)", d, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Margin ratio %s failed: %s", d, exc)
        time.sleep(2)
    if not by_date:
        return None
    rows = sorted(by_date.values(), key=lambda r: r["date"])
    prev = None
    for r in rows:
        r["ratio_change"] = round(r["ratio"] - prev["ratio"], 2) if prev else None
        prev = r
    data = {
        "market": "上市（TWSE，含上市 ETF）",
        "method": "Σ(融資餘額張×1000×收盤價) ÷ 融資金額",
        "source": [MARGN_URL, INDEX_URL],
        "updated_at": now_taipei_iso(),
        "rows": rows,
    }
    if added:
        write_json(path, data)
        write_json(cp, last_closes)
    return data


def build_margin_view(root: Path, recent: int = 10, full: int = 60) -> dict[str, Any] | None:
    path = ratio_path(root)
    if not path.is_file():
        return None
    rows = read_json(path).get("rows") or []
    if not rows:
        return None
    return {
        "latest": rows[-1],
        "recent": list(reversed(rows[-recent:])),
        "full": list(reversed(rows[-full:])),
        "chart": rows[-full:],
        "source_page": SOURCE_PAGE,
    }
