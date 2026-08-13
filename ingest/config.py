"""Shared paths and the company list that drives every ingest run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
WAREHOUSE = DATA_DIR / "warehouse.duckdb"
COMPANIES_FILE = REPO_ROOT / "companies.yml"


@dataclass(frozen=True)
class Company:
    name: str
    token: str
    ats: str
    segment: str


def load_companies(only: str | None = None) -> list[Company]:
    """Read companies.yml. `only` filters to a single ATS or company token."""
    raw = yaml.safe_load(COMPANIES_FILE.read_text(encoding="utf-8"))
    companies = [Company(**entry) for entry in raw["companies"]]
    if only:
        companies = [c for c in companies if only in (c.ats, c.token)]
    return companies
