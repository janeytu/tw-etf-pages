"""Download official Excel holdings (with WAF warmup / retries) + zdsetf fallback."""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import requests

from .config import AppConfig, EtfConfig
from .utils import today_taipei

logger = logging.getLogger(__name__)

UNI_WARMUP = "https://www.ezmoney.com.tw/"
UNI_EXCEL = "https://www.ezmoney.com.tw/ETF/Fund/AssetExcelNPOI?fundCode={fund_code}"
FH_EXCEL = "https://www.fhtrust.com.tw/api/assetsExcel/{fund_code}/{yyyymmdd}"
ZDSETF_SNAPSHOT = "https://zdsetf.com/api/etfs/{ticker}/snapshot"
YUANTA_RATIO = "https://www.yuantaetfs.com/product/detail/{ticker}/ratio"
CATHAY_CWAPI = "https://cwapi.cathaysite.com.tw"
CATHAY_WEIGHTS = CATHAY_CWAPI + "/api/ETF/GetIndexStockWeights"
# cwapi/Akamai blocks non-browser User-Agents (project UA → 403).
CATHAY_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

UOBAM_BASE = "https://www.uobam.com.tw"
UOBAM_PCF_API = UOBAM_BASE + "/json/reply/WebSitePcfRequest"
UOBAM_BROWSER_UA = CATHAY_BROWSER_UA

KGI_BASE = "https://www.kgifund.com.tw"
KGI_FUND_DETAIL = KGI_BASE + "/Fund/Detail?fundID={fund_code}"
KGI_BROWSER_UA = CATHAY_BROWSER_UA

CAPITAL_BASE = "https://www.capitalfund.com.tw"
CAPITAL_BUYBACK = CAPITAL_BASE + "/CFWeb/api/etf/buyback"

# Node extracts FundWeights from Nuxt SSR window.__NUXT__ (packed IIFE; not pure-JSON).
_YUANTA_EXTRACT_JS = r"""
const fs = require('fs');
const html = fs.readFileSync(process.argv[1], 'utf8');
const m = html.match(/<script>window\.__NUXT__=(.*?)<\/script>/s);
if (!m) { console.error('yuanta: missing window.__NUXT__'); process.exit(2); }
const nuxt = eval(m[1]);
const pages = (nuxt && nuxt.data) || [];
let wd = null;
for (const page of pages) {
  if (page && page.weightData && page.weightData.FundWeights) { wd = page.weightData; break; }
}
if (!wd) { console.error('yuanta: weightData.FundWeights not found'); process.exit(3); }
const pcf = wd.PCF || {};
const fw = wd.FundWeights || {};
const stocks = fw.StockWeights || [];
const futures = fw.FutureWeights || [];
const tr = String(pcf.trandate || '');
const snapshot_date = /^\d{8}$/.test(tr)
  ? tr.replace(/(\d{4})(\d{2})(\d{2})/, '$1-$2-$3')
  : tr;
const out = {
  source_url: process.argv[2] || '',
  ticker: process.argv[3] || String(pcf.markcd || ''),
  snapshot_date,
  fundid: pcf.fundid,
  fundname: pcf.fundname,
  markcd: pcf.markcd,
  upddate: pcf.upddate,
  summary: fw.Summary || null,
  holdings: stocks.map((h) => ({
    stock_code: String(h.code),
    stock_name: h.name,
    shares: h.qty,
    weight_pct: h.weights,
  })),
  futures: futures.map((h) => ({
    code: h.code,
    name: h.name,
    shares: h.qty,
    weight_pct: h.weights,
    ym: h.ym,
  })),
};
process.stdout.write(JSON.stringify(out));
"""



class FetchError(RuntimeError):
    pass


def _session(cfg: AppConfig) -> requests.Session:
    s = requests.Session()
    ua = cfg.fetch.get(
        "user_agent",
        "tw-etf-pages/1.0 (public ETF holdings archive)",
    )
    s.headers.update(
        {
            "User-Agent": ua,
            "Accept": "*/*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
    )
    return s


def _retry_get(
    session: requests.Session,
    url: str,
    *,
    retries: int,
    backoff: float,
    timeout: float,
    **kwargs: Any,
) -> requests.Response:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout, **kwargs)
            return resp
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("GET %s attempt %s/%s failed: %s", url, attempt, retries, exc)
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise FetchError(f"GET failed after {retries} tries: {url}: {last_exc}")


def fetch_uni_excel(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Warm WAF cookie jar, then download Uni AssetExcelNPOI."""
    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)

    logger.info("Uni WAF warmup for %s", etf.ticker)
    warm = _retry_get(session, UNI_WARMUP, retries=retries, backoff=backoff, timeout=timeout)
    if warm.status_code >= 400:
        logger.warning("warmup status %s (continuing)", warm.status_code)

    url = UNI_EXCEL.format(fund_code=etf.fund_code)
    logger.info("Downloading Uni Excel %s → %s", url, dest)
    resp = _retry_get(session, url, retries=retries, backoff=backoff, timeout=timeout)
    if resp.status_code != 200:
        raise FetchError(f"Uni Excel HTTP {resp.status_code} for {etf.ticker}: {url}")
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ctype and len(resp.content) < 5000:
        raise FetchError(f"Uni Excel looks like HTML challenge for {etf.ticker}")
    if len(resp.content) < 1000:
        raise FetchError(f"Uni Excel too small ({len(resp.content)} bytes) for {etf.ticker}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def fetch_fh_excel(
    cfg: AppConfig,
    etf: EtfConfig,
    dest: Path,
    as_of: date | None = None,
    lookback_days: int = 7,
) -> Path:
    """Download FH Excel for as_of (default today), walking back if empty."""
    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)

    start = as_of or today_taipei()
    errors: list[str] = []
    for delta in range(lookback_days + 1):
        d = start - timedelta(days=delta)
        ymd = d.strftime("%Y%m%d")
        url = FH_EXCEL.format(fund_code=etf.fund_code, yyyymmdd=ymd)
        logger.info("Trying FH Excel %s", url)
        resp = _retry_get(session, url, retries=retries, backoff=backoff, timeout=timeout)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        body = resp.content
        # empty / 查無資料 JSON
        if "json" in ctype or body[:1] == b"{":
            errors.append(f"{ymd}: no data yet ({body[:80]!r})")
            continue
        if resp.status_code != 200:
            errors.append(f"{ymd}: HTTP {resp.status_code}")
            continue
        if len(body) < 500:
            errors.append(f"{ymd}: too small ({len(body)})")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return dest

    raise FetchError(
        f"FH Excel unavailable for {etf.ticker} in last {lookback_days} days: "
        + "; ".join(errors[-3:])
    )


def fetch_zdsetf_snapshot(cfg: AppConfig, ticker: str, dest: Path) -> Path:
    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    url = ZDSETF_SNAPSHOT.format(ticker=ticker)
    logger.info("zdsetf snapshot %s", url)
    resp = _retry_get(session, url, retries=retries, backoff=backoff, timeout=timeout)
    if resp.status_code != 200:
        raise FetchError(f"zdsetf HTTP {resp.status_code}: {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest



def fetch_yuanta_ratio(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Download YuantaETFs ratio SSR page and extract FundWeights JSON via Node.

    Official page embeds holdings in window.__NUXT__ (Nuxt 2 packed payload).
    There is no stable public Excel/CSV URL; zdsetf does not track passive 0050.
    Requires Node.js on PATH (preinstalled on GitHub-hosted Ubuntu runners).
    """
    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    url = etf.source_page or YUANTA_RATIO.format(ticker=etf.ticker)
    logger.info("Yuanta ratio page %s", url)
    html = ""
    req_err: Exception | None = None
    try:
        # Single attempt: Yuanta cert chain fails SSL verify on some OpenSSL builds
        # (Missing Subject Key Identifier). Fall back to curl quickly.
        resp = session.get(url, timeout=timeout)
        if resp.status_code != 200:
            raise FetchError(f"Yuanta ratio HTTP {resp.status_code}: {url}")
        html = resp.text
    except Exception as exc:  # noqa: BLE001 — SSL or transport → curl fallback
        req_err = exc
        logger.warning("Yuanta requests GET failed (%s); trying curl", exc)
        try:
            proc = subprocess.run(
                [
                    "curl", "-fsSL", "--max-time", str(int(timeout)),
                    "-A", session.headers.get("User-Agent", "tw-etf-pages/1.0"),
                    url,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as curl_exc:
            raise FetchError(
                f"Yuanta ratio fetch failed (requests+curl): {req_err}"
            ) from curl_exc
        if proc.returncode != 0:
            raise FetchError(
                f"Yuanta curl failed rc={proc.returncode}: {proc.stderr[:300]!r} "
                f"(requests: {req_err})"
            ) from req_err
        html = proc.stdout
    if "window.__NUXT__" not in html:
        raise FetchError(f"Yuanta ratio missing __NUXT__ for {etf.ticker}")
    if len(html) < 5000:
        raise FetchError(f"Yuanta ratio HTML too small ({len(html)}) for {etf.ticker}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    html_path = dest.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", "-e", _YUANTA_EXTRACT_JS, str(html_path), url, etf.ticker],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FetchError(
            "Yuanta extract requires Node.js on PATH (node -e ...)"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FetchError(f"Yuanta Node extract timed out for {etf.ticker}") from exc
    if proc.returncode != 0:
        raise FetchError(
            f"Yuanta Node extract failed for {etf.ticker}: "
            f"rc={proc.returncode} stderr={proc.stderr[:500]!r}"
        )
    raw = proc.stdout.strip()
    if not raw.startswith("{"):
        raise FetchError(f"Yuanta extract did not return JSON for {etf.ticker}")
    dest.write_text(raw + "\n", encoding="utf-8")
    return dest



def fetch_cathay_weights(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Download Cathay cwapi GetIndexStockWeights JSON (official 持股權重).

    Used when zdsetf does not track the ticker (typical for Cathay passives
    such as 00881). Requires fund_code = cwapi fundCode (e.g. CR for 00881;
    page slug may be ECR). Shares are not disclosed; we synthesize
    shares = round(weight_pct * 1e6) for relative day-to-day tracking.
    """
    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    session.headers["User-Agent"] = CATHAY_BROWSER_UA
    session.headers["Referer"] = etf.source_page or "https://www.cathaysite.com.tw/"
    session.headers["Accept"] = "application/json, text/plain, */*"
    fund_code = (etf.fund_code or "").strip()
    if not fund_code:
        raise FetchError(f"Cathay weights require fund_code for {etf.ticker}")
    url = CATHAY_WEIGHTS
    params = {"fundCode": fund_code}
    logger.info("Cathay weights %s fundCode=%s", url, fund_code)
    resp = _retry_get(
        session, url, retries=retries, backoff=backoff, timeout=timeout, params=params
    )
    if resp.status_code != 200:
        raise FetchError(f"Cathay weights HTTP {resp.status_code}: {url}?fundCode={fund_code}")
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Cathay weights non-JSON for {etf.ticker}") from exc
    if str(payload.get("returnCode")) != "2000" or not payload.get("success"):
        raise FetchError(
            f"Cathay weights API error for {etf.ticker}: "
            f"returnCode={payload.get('returnCode')} "
            f"msg={payload.get('returnMessage')!r}"
        )
    result = payload.get("result") or {}
    rows = result.get("stockWeights") or []
    if not isinstance(rows, list) or not rows:
        raise FetchError(f"Cathay weights empty stockWeights for {etf.ticker}")
    raw_date = result.get("date") or ""
    ds = str(raw_date).strip().replace("/", "-")
    holdings = []
    for h in rows:
        if not isinstance(h, dict):
            continue
        code = h.get("stockCode") or h.get("stock_code")
        if code is None or str(code).strip() == "":
            continue
        try:
            w = float(h.get("weights") if h.get("weights") is not None else h.get("weight_pct") or 0)
        except (TypeError, ValueError):
            w = 0.0
        holdings.append(
            {
                "stock_code": str(code).strip(),
                "stock_name": h.get("stockName") or h.get("stock_name") or "",
                "shares": int(round(w * 1_000_000)),
                "weight_pct": w,
            }
        )
    if not holdings:
        raise FetchError(f"Cathay weights parsed 0 holdings for {etf.ticker}")
    out = {
        "source_url": etf.source_page
        or f"https://www.cathaysite.com.tw/ETF/detail/{fund_code}",
        "api_url": f"{url}?fundCode={fund_code}",
        "ticker": etf.ticker,
        "fund_code": fund_code,
        "snapshot_date": ds,
        "holdings": holdings,
        "shares_note": "synthetic_from_weight_pct_x_1e6",
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        __import__("json").dumps(out, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return dest




def fetch_uobam_pcf(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Download UOBAM (大華銀投信) official WebSitePcfRequest JSON.

    zdsetf does not track passive 00918. Official PCF API returns equity
    holdings with real share counts (qty) and weight_pct. Non-stock rows
    (Cash / Margin) are dropped at parse time.

    Some OpenSSL/CA bundles lack the Chunghwa Telecom intermediate used by
    uobam.com.tw; on SSL failure we retry with verify=False (same class of
    workaround as Yuanta curl fallback).
    """
    import json
    import re
    from datetime import datetime, timezone, timedelta
    import urllib3

    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    session.headers["User-Agent"] = UOBAM_BROWSER_UA
    session.headers["Referer"] = etf.source_page or (UOBAM_BASE + "/")
    session.headers["Accept"] = "application/json, text/plain, */*"
    fund_code = (etf.fund_code or "").strip()
    if not fund_code:
        raise FetchError(f"UOBAM PCF requires fund_code for {etf.ticker}")
    url = UOBAM_PCF_API
    params = {"fundID": fund_code}
    logger.info("UOBAM PCF %s fundID=%s", url, fund_code)

    resp = None
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        for verify in (True, False):
            try:
                if not verify:
                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                resp = session.get(url, params=params, timeout=timeout, verify=verify)
                if not verify:
                    logger.warning(
                        "UOBAM PCF SSL verify disabled for %s (incomplete CA chain)",
                        etf.ticker,
                    )
                last_exc = None
                break
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning(
                    "UOBAM GET verify=%s attempt %s/%s failed: %s",
                    verify,
                    attempt,
                    retries,
                    exc,
                )
        if resp is not None:
            break
        if attempt < retries:
            time.sleep(backoff * attempt)
    if resp is None:
        raise FetchError(f"UOBAM PCF GET failed after {retries} tries: {url}: {last_exc}")
    if resp.status_code != 200:
        raise FetchError(f"UOBAM PCF HTTP {resp.status_code}: {url}?fundID={fund_code}")
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"UOBAM PCF non-JSON for {etf.ticker}") from exc
    rows = payload.get("result") or []
    if not isinstance(rows, list) or not rows:
        raise FetchError(f"UOBAM PCF empty result for {etf.ticker}")

    def _dotnet_date_to_iso(raw: object) -> str:
        m = re.search(r"/Date\((\d+)", str(raw or ""))
        if not m:
            return ""
        ms = int(m.group(1))
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone(timedelta(hours=8)))
        return dt.strftime("%Y-%m-%d")

    ds = _dotnet_date_to_iso(payload.get("datadate")) or _dotnet_date_to_iso(
        payload.get("publish")
    )
    if not ds:
        raise FetchError(f"UOBAM PCF missing datadate for {etf.ticker}")

    holdings = []
    for h in rows:
        if not isinstance(h, dict):
            continue
        if str(h.get("kind") or "").lower() != "stock":
            continue
        code = h.get("code") or h.get("stock_code")
        if code is None or str(code).strip() == "":
            continue
        code_s = str(code).strip()
        if not any(ch.isdigit() for ch in code_s):
            continue
        try:
            w = float(h.get("weight") if h.get("weight") is not None else h.get("weight_pct") or 0)
        except (TypeError, ValueError):
            w = 0.0
        qty_raw = h.get("qty", h.get("shares", 0))
        try:
            if isinstance(qty_raw, (int, float)):
                shares = int(round(float(qty_raw)))
            else:
                s = str(qty_raw or "0").replace(",", "").strip()
                shares = int(round(float(s))) if s and s != "-" else 0
        except (TypeError, ValueError):
            shares = 0
        holdings.append(
            {
                "stock_code": code_s,
                "stock_name": h.get("cName") or h.get("stock_name") or h.get("name") or "",
                "shares": shares,
                "weight_pct": w,
            }
        )
    if not holdings:
        raise FetchError(f"UOBAM PCF parsed 0 stock holdings for {etf.ticker}")

    out = {
        "source_url": etf.source_page
        or f"{UOBAM_BASE}/fund/etf/pcf?fundID={fund_code}",
        "api_url": f"{url}?fundID={fund_code}",
        "ticker": etf.ticker,
        "fund_code": fund_code,
        "etf002": payload.get("etf002") or etf.ticker,
        "twName": payload.get("twName"),
        "snapshot_date": ds,
        "holdings": holdings,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest



def fetch_capital_buyback(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Download Capital Fund (群益投信) official CFWeb /api/etf/buyback JSON.

    Used when zdsetf does not track the ticker (typical for Capital passives
    such as 00919). Requires fund_code = official product id (e.g. 195 for
    00919; same id as /etf/product/detail/{id}/portfolio). Returns equity
    stocks with real share counts and weights; bonds/futures/RP omitted.
    As-of date uses pcf.date2 (portfolio date shown on the official page).
    """
    import json

    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    session.headers["Accept"] = "application/json, text/plain, */*"
    session.headers["Content-Type"] = "application/json"
    session.headers["Referer"] = etf.source_page or (CAPITAL_BASE + "/")
    fund_code = (etf.fund_code or "").strip()
    if not fund_code:
        raise FetchError(f"Capital buyback requires fund_code for {etf.ticker}")
    # API accepts numeric or string fundId
    try:
        fund_id_payload: int | str = int(fund_code)
    except ValueError:
        fund_id_payload = fund_code
    url = CAPITAL_BUYBACK
    logger.info("Capital buyback %s fundId=%s", url, fund_code)

    resp = None
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.post(
                url, json={"fundId": fund_id_payload}, timeout=timeout
            )
            last_exc = None
            break
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                "Capital buyback POST attempt %s/%s failed: %s",
                attempt,
                retries,
                exc,
            )
            if attempt < retries:
                time.sleep(backoff * attempt)
    if resp is None:
        raise FetchError(
            f"Capital buyback POST failed after {retries} tries: {url}: {last_exc}"
        )
    if resp.status_code != 200:
        raise FetchError(
            f"Capital buyback HTTP {resp.status_code}: {url} fundId={fund_code}"
        )
    try:
        payload = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"Capital buyback non-JSON for {etf.ticker}") from exc
    if payload.get("code") not in (200, "200"):
        raise FetchError(
            f"Capital buyback API error for {etf.ticker}: "
            f"code={payload.get('code')} msg={payload.get('message')!r}"
        )
    data = payload.get("data") or {}
    pcf = data.get("pcf") or {}
    rows = data.get("stocks") or []
    if not isinstance(rows, list) or not rows:
        raise FetchError(f"Capital buyback empty stocks for {etf.ticker}")

    raw_date = pcf.get("date2") or pcf.get("date1") or ""
    ds = str(raw_date).strip().replace("/", "-")
    if not ds:
        raise FetchError(f"Capital buyback missing date2 for {etf.ticker}")

    holdings = []
    for h in rows:
        if not isinstance(h, dict):
            continue
        code = h.get("stocNo") or h.get("stock_code") or h.get("code")
        if code is None or str(code).strip() == "":
            continue
        code_s = str(code).strip()
        if not any(ch.isdigit() for ch in code_s):
            continue
        try:
            w_raw = h.get("weightRound")
            if w_raw is None:
                w_raw = h.get("weight")
            if w_raw is None:
                w_raw = h.get("weight_pct")
            w = float(w_raw or 0)
        except (TypeError, ValueError):
            w = 0.0
        qty_raw = h.get("share", h.get("shares", 0))
        try:
            if isinstance(qty_raw, (int, float)):
                shares = int(round(float(qty_raw)))
            else:
                s = str(qty_raw or "0").replace(",", "").strip()
                shares = int(round(float(s))) if s and s != "-" else 0
        except (TypeError, ValueError):
            shares = 0
        holdings.append(
            {
                "stock_code": code_s,
                "stock_name": h.get("stocName") or h.get("stock_name") or h.get("name") or "",
                "shares": shares,
                "weight_pct": w,
            }
        )
    if not holdings:
        raise FetchError(f"Capital buyback parsed 0 stock holdings for {etf.ticker}")

    out = {
        "source_url": etf.source_page
        or f"{CAPITAL_BASE}/etf/product/detail/{fund_code}/portfolio",
        "api_url": url,
        "ticker": etf.ticker,
        "fund_code": fund_code,
        "fund_name": pcf.get("fundName"),
        "snapshot_date": ds,
        "holdings": holdings,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest




class _NonStrictX509Adapter(requests.adapters.HTTPAdapter):
    """HTTPS adapter that keeps full certificate verification but clears
    VERIFY_X509_STRICT (default on Python 3.13+).

    kgifund.com.tw serves a CA chain whose intermediate lacks a Subject Key
    Identifier, which strict mode rejects ("Missing Subject Key Identifier")
    although the chain is otherwise valid (curl / browsers accept it).
    """

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
        import ssl

        ctx = ssl.create_default_context()
        strict = getattr(ssl, "VERIFY_X509_STRICT", 0)
        if strict:
            ctx.verify_flags &= ~strict
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def fetch_kgi_holdings(cfg: AppConfig, etf: EtfConfig, dest: Path) -> Path:
    """Download KGI (凱基投信) official Fund/Detail page and extract stock holdings.

    zdsetf does not track passive 009816 (404). The official fund detail page
    (server-rendered HTML, ``/Fund/Detail?fundID=J023``) carries the 持股比重
    section with a dated stock table (股票代號／股票名稱／股數／權重(%)), i.e.
    real share counts and weights. Futures / cash rows are not part of the
    stock table and are ignored.
    """
    import html as _html
    import json
    import re

    timeout = float(cfg.fetch.get("timeout_sec", 60))
    retries = int(cfg.fetch.get("retries", 3))
    backoff = float(cfg.fetch.get("retry_backoff_sec", 2))
    session = _session(cfg)
    session.mount(KGI_BASE, _NonStrictX509Adapter())
    session.headers["User-Agent"] = KGI_BROWSER_UA
    session.headers["Accept"] = "text/html,application/xhtml+xml,*/*;q=0.8"
    fund_code = (etf.fund_code or "").strip()
    if not fund_code:
        raise FetchError(f"KGI fund detail requires fund_code for {etf.ticker}")
    url = KGI_FUND_DETAIL.format(fund_code=fund_code)
    logger.info("KGI fund detail %s", url)
    resp = _retry_get(session, url, retries=retries, backoff=backoff, timeout=timeout)
    if resp.status_code != 200:
        raise FetchError(f"KGI fund detail HTTP {resp.status_code}: {url}")
    resp.encoding = resp.encoding or "utf-8"
    text = resp.text

    def _cell(raw: str) -> str:
        return _html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()

    # Date shown under the 持股比重 title, e.g. <p class="fund-asset__date">(2026/10/12)</p>
    sec = text.find('id="FundDetail-06"')
    m_date = re.search(r'fund-asset__date">\s*\((\d{4}/\d{1,2}/\d{1,2})\)', text[sec:] if sec >= 0 else text)
    if not m_date:
        raise FetchError(f"KGI fund detail missing holdings date for {etf.ticker}")
    y, mo, d = (int(x) for x in m_date.group(1).split("/"))
    ds = f"{y:04d}-{mo:02d}-{d:02d}"

    holdings: list[dict[str, Any]] = []
    for body in re.findall(r"<table[^>]*>(.*?)</table>", text, re.S):
        heads = [_cell(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
        if not heads or heads[0] != "股票代號":
            continue
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            cells = [_cell(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(cells) < 4:
                continue
            code_s = cells[0].strip().upper()
            if not code_s or not any(ch.isdigit() for ch in code_s):
                continue
            try:
                shares = int(round(float(cells[2].replace(",", "") or 0)))
            except ValueError:
                shares = 0
            try:
                w = float(cells[3].replace(",", "").replace("%", "") or 0)
            except ValueError:
                w = 0.0
            holdings.append(
                {
                    "stock_code": code_s,
                    "stock_name": cells[1],
                    "shares": shares,
                    "weight_pct": w,
                }
            )
        if holdings:
            break  # first stock table only (avoid duplicate desktop/mobile copies)
    if not holdings:
        raise FetchError(f"KGI fund detail parsed 0 stock holdings for {etf.ticker}")

    out = {
        "source_url": etf.source_page or url,
        "api_url": url,
        "ticker": etf.ticker,
        "fund_code": fund_code,
        "fund_name": etf.name,
        "snapshot_date": ds,
        "holdings": holdings,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def fetch_etf_holdings(
    cfg: AppConfig,
    etf: EtfConfig,
    *,
    allow_fallback: bool = True,
) -> tuple[Path, str]:
    """
    Fetch primary issuer Excel; on failure optionally fallback to zdsetf JSON.
    Returns (path, kind) where kind is 'uni_excel' | 'fh_excel' | 'zdsetf' | 'yuanta' | 'cathay' | 'uobam' | 'kgi' | 'capital'.

    Capital Fund (群益投信), Fubon (富邦投信), CTBC (中國信託投信),
    Nomura (野村投信), Allianz (安聯投信), Cathay (國泰投信),
    J.P. Morgan AM Taiwan / 摩根投信 (jpm), Taishin / 台新投信 (taishin),
    First Securities Investment Trust / 第一金投信 (fsitc),
    and Mega Funds / 兆豐投信 (mega)
    have no reliable public Excel/CSV download URL for automation; for issuer in
    {"fubon", "ctbc", "nomura", "allianz", "jpm", "taishin", "fsitc", "mega"}
    we archive via zdsetf.com snapshot, which mirrors the official portfolio/PCF
    page (source_url points at websys.fsit.com.tw /
    ctbcinvestments.com / nomurafunds.com.tw / etf.allianzgi.com.tw /
    am.jpmorgan.com / tsit.com.tw / fsitc.com.tw / megafunds.com.tw).
    Capital (capital): try zdsetf first (actives like 00992A); on failure use
    official CFWeb /api/etf/buyback (passives like 00919; real shares).
    Cathay (cathay): try zdsetf first; on failure use official cwapi
    GetIndexStockWeights (passives like 00881; weights only, synthetic shares).
    """
    stamp = today_taipei().isoformat()
    raw_dir = cfg.raw_dir / etf.ticker

    # Primary path for UOBAM / 大華銀投信 passive ETFs: official WebSitePcfRequest.
    # zdsetf does not track 00918 (404).
    if etf.issuer == "uobam":
        path = raw_dir / f"{etf.ticker}_{stamp}_uobam.json"
        fetch_uobam_pcf(cfg, etf, path)
        return path, "uobam"

    # Primary path for KGI / 凱基投信 passive ETFs: official Fund/Detail HTML 持股比重.
    # zdsetf does not track 009816 (404).
    if etf.issuer == "kgi":
        path = raw_dir / f"{etf.ticker}_{stamp}_kgi.json"
        fetch_kgi_holdings(cfg, etf, path)
        return path, "kgi"

    # Primary path for Yuanta (元大投信) passive ETFs: official ratio SSR → JSON.
    if etf.issuer == "yuanta":
        path = raw_dir / f"{etf.ticker}_{stamp}_yuanta.json"
        fetch_yuanta_ratio(cfg, etf, path)
        return path, "yuanta"

    # Cathay: prefer zdsetf when available (actives like 00400A have share counts).
    # Passives such as 00881 are not on zdsetf → official cwapi GetIndexStockWeights.
    if etf.issuer == "cathay":
        path_z = raw_dir / f"{etf.ticker}_{stamp}_zdsetf.json"
        try:
            fetch_zdsetf_snapshot(cfg, etf.ticker, path_z)
            return path_z, "zdsetf"
        except FetchError as exc:
            logger.warning(
                "Cathay zdsetf unavailable for %s (%s); trying official weights",
                etf.ticker,
                exc,
            )
            path_c = raw_dir / f"{etf.ticker}_{stamp}_cathay.json"
            fetch_cathay_weights(cfg, etf, path_c)
            return path_c, "cathay"

    # Capital: prefer zdsetf when available (actives like 00992A / 00982A).
    # Passives such as 00919 are not on zdsetf → official CFWeb buyback API
    # (real share qty + weights; fund_code = product id e.g. 195).
    if etf.issuer == "capital":
        path_z = raw_dir / f"{etf.ticker}_{stamp}_zdsetf.json"
        try:
            fetch_zdsetf_snapshot(cfg, etf.ticker, path_z)
            return path_z, "zdsetf"
        except FetchError as exc:
            logger.warning(
                "Capital zdsetf unavailable for %s (%s); trying official buyback",
                etf.ticker,
                exc,
            )
            path_c = raw_dir / f"{etf.ticker}_{stamp}_capital.json"
            fetch_capital_buyback(cfg, etf, path_c)
            return path_c, "capital"

    # Primary path for fubon / ctbc / nomura / allianz / jpm / taishin / fsitc / mega: zdsetf mirror (no Excel API).
    if etf.issuer in ("fubon", "ctbc", "nomura", "allianz", "jpm", "taishin", "fsitc", "mega"):
        path = raw_dir / f"{etf.ticker}_{stamp}_zdsetf.json"
        fetch_zdsetf_snapshot(cfg, etf.ticker, path)
        return path, "zdsetf"

    try:
        if etf.issuer == "uni":
            path = raw_dir / f"{etf.ticker}_{stamp}_uni.xlsx"
            fetch_uni_excel(cfg, etf, path)
            return path, "uni_excel"
        if etf.issuer == "fh":
            path = raw_dir / f"{etf.ticker}_{stamp}_fh.xlsx"
            fetch_fh_excel(cfg, etf, path)
            return path, "fh_excel"
        raise FetchError(f"unknown issuer {etf.issuer}")
    except FetchError as exc:
        logger.error("Primary fetch failed for %s: %s", etf.ticker, exc)
        if not allow_fallback:
            raise
        path = raw_dir / f"{etf.ticker}_{stamp}_zdsetf.json"
        fetch_zdsetf_snapshot(cfg, etf.ticker, path)
        return path, "zdsetf"
