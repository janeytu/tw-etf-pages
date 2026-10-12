"""Minimal tests: config loads 009816; parse_kgi on saved sample."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tw_etf_pages.config import load_config
from tw_etf_pages.parse import parse_kgi_holdings


def test_config_loads_009816_kgi():
    cfg = load_config(ROOT)
    etf = cfg.etf("009816")
    assert etf.name == "凱基台灣TOP50"
    assert etf.issuer == "kgi"
    assert etf.fund_code == "J023"
    assert "kgifund.com.tw" in etf.source_page
    assert "J023" in etf.source_page


def test_parse_kgi_009816_sample():
    cfg = load_config(ROOT)
    path = ROOT / "samples" / "kgi_009816_holdings.json"
    assert path.is_file(), "missing samples/kgi_009816_holdings.json"
    snap = parse_kgi_holdings(path, "009816", cfg.placeholder)
    assert snap["etf_ticker"] == "009816"
    assert snap["source"] == "kgi"
    assert snap["as_of_date"]  # non-empty ISO date
    assert snap["holdings_count"] == 50  # TOP 50 index
    codes = {h["stock_code"] for h in snap["holdings"]}
    assert "2330" in codes
    assert all(isinstance(h["weight_pct"], float) for h in snap["holdings"])
    top = max(snap["holdings"], key=lambda h: h["weight_pct"])
    assert top["stock_code"] == "2330"
    assert top["shares"] > 0  # real share count from official page
    meta = snap.get("meta") or {}
    assert "kgifund.com.tw" in str(meta.get("source_url") or meta.get("api_url") or "")


if __name__ == "__main__":
    test_config_loads_009816_kgi()
    test_parse_kgi_009816_sample()
    print("OK")
