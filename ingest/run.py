"""Fetch one snapshot of every tracked job board.

Each run writes `data/raw/<snapshot_date>/<ats>__<token>.json`. Runs are
idempotent per day: re-running overwrites that day's file rather than appending,
so a failed midday run can simply be repeated.

A board that has moved ATS or gone quiet is logged and skipped — one dead
company must never take down the whole snapshot.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingest.config import RAW_DIR, Company, load_companies
from ingest.sources import FETCHERS

USER_AGENT = "job-market-intel/0.1 (personal data pipeline)"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# Retry transient failures only. A 404 means the board is genuinely gone, so
# retrying it just wastes 3 round trips.
RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRYABLE),
    reraise=True,
)
def _fetch(client: httpx.Client, company: Company) -> list[dict]:
    return FETCHERS[company.ats](client, company)


def fetch_company(client: httpx.Client, company: Company, snapshot_date: date) -> int | None:
    """Fetch and persist one board. Returns posting count, or None if skipped."""
    try:
        jobs = _fetch(client, company)
    except httpx.HTTPStatusError as exc:
        print(f"  SKIP  {company.name:<12} HTTP {exc.response.status_code}", file=sys.stderr)
        return None
    except Exception as exc:  # noqa: BLE001 - one bad board shouldn't kill the run
        print(f"  SKIP  {company.name:<12} {type(exc).__name__}: {exc}", file=sys.stderr)
        return None

    envelope = {
        "company_name": company.name,
        "company_token": company.token,
        "ats": company.ats,
        "segment": company.segment,
        "snapshot_date": snapshot_date.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(),
        "posting_count": len(jobs),
        "jobs": jobs,
    }

    out_dir = RAW_DIR / snapshot_date.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{company.ats}__{company.token}.json"
    out_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

    size_mb = out_path.stat().st_size / 1_048_576
    print(f"  ok    {company.name:<12} {len(jobs):>4} postings  ({size_mb:.1f} MB)")
    return len(jobs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="limit to one ATS ('ashby') or company token ('stripe')")
    parser.add_argument("--date", help="override snapshot date (YYYY-MM-DD), for backfills")
    args = parser.parse_args()

    snapshot_date = date.fromisoformat(args.date) if args.date else date.today()
    companies = load_companies(only=args.only)

    print(f"Snapshot {snapshot_date} — {len(companies)} boards")

    total, skipped = 0, 0
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT) as client:
        for company in companies:
            count = fetch_company(client, company, snapshot_date)
            if count is None:
                skipped += 1
            else:
                total += count

    print(f"\n{total:,} postings from {len(companies) - skipped} boards ({skipped} skipped)")
    print(f"Written to {RAW_DIR / snapshot_date.isoformat()}")

    # Fail loudly if most boards died — that is a pipeline problem, not a data one.
    if companies and skipped > len(companies) / 2:
        print("ERROR: majority of boards failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
