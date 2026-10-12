"""Load project config.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class EtfConfig:
    ticker: str
    name: str
    issuer: str  # uni | fh | capital | fubon | ctbc | nomura | allianz | cathay | jpm | taishin | fsitc | mega | yuanta | uobam | kgi
    fund_code: str
    source_page: str


@dataclass(frozen=True)
class PlaceholderPolicy:
    max_shares: int
    max_weight_pct: float
    exclude_from_changes: bool


@dataclass(frozen=True)
class AppConfig:
    root: Path
    timezone: str
    etfs: list[EtfConfig]
    placeholder: PlaceholderPolicy
    fetch: dict[str, Any]
    snapshots_dir: Path
    changes_dir: Path
    raw_dir: Path
    site_dir: Path
    samples_dir: Path

    def etf(self, ticker: str) -> EtfConfig:
        for e in self.etfs:
            if e.ticker == ticker:
                return e
        raise KeyError(ticker)


def load_config(root: Path | None = None) -> AppConfig:
    root = root or ROOT
    raw = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    ph = raw.get("placeholder", {})
    paths = raw.get("paths", {})
    etfs = [
        EtfConfig(
            ticker=e["ticker"],
            name=e["name"],
            issuer=e["issuer"],
            fund_code=e["fund_code"],
            source_page=e.get("source_page", ""),
        )
        for e in raw["etfs"]
    ]
    return AppConfig(
        root=root,
        timezone=raw.get("timezone", "Asia/Taipei"),
        etfs=etfs,
        placeholder=PlaceholderPolicy(
            max_shares=int(ph.get("max_shares", 1000)),
            max_weight_pct=float(ph.get("max_weight_pct", 0.01)),
            exclude_from_changes=bool(ph.get("exclude_from_changes", True)),
        ),
        fetch=dict(raw.get("fetch", {})),
        snapshots_dir=root / paths.get("snapshots_dir", "data/snapshots"),
        changes_dir=root / paths.get("changes_dir", "data/changes"),
        raw_dir=root / paths.get("raw_dir", "data/raw"),
        site_dir=root / paths.get("site_dir", "site"),
        samples_dir=root / paths.get("samples_dir", "samples"),
    )
