"""Convert a day's raw JSON into the committed parquet store.

Why this layer exists
---------------------
GitHub Actions runners are ephemeral, so anything the pipeline needs to
remember between runs has to be committed. The raw JSON is 66 MB *per day* —
committing that would push the repo past a gigabyte within a month.

Almost all of that weight is job descriptions, which do not change from one day
to the next. So the store is split:

  store/snapshots/<date>.parquet   thin: which postings were open that day
  store/payloads/<date>.parquet    heavy: full API payloads, written once

A payload is stored the first time a given (posting_key, payload_hash) pair is
seen. Hashing rather than keying on posting_key alone means an edited posting
gets a second row instead of being silently frozen at its original text — and
because the snapshot records which hash was live on which day, the warehouse
can be rebuilt exactly as it looked on any past date.

Steady state is roughly 1 MB per day instead of 66 MB.
"""

from __future__ import annotations

import argparse
import sys

import duckdb

from ingest.config import RAW_DIR, REPO_ROOT

STORE_DIR = REPO_ROOT / "store"
SNAPSHOT_DIR = STORE_DIR / "snapshots"
PAYLOAD_DIR = STORE_DIR / "payloads"

ENVELOPE_COLUMNS = """{
    company_name:  'VARCHAR',
    company_token: 'VARCHAR',
    ats:           'VARCHAR',
    segment:       'VARCHAR',
    snapshot_date: 'DATE',
    fetched_at:    'TIMESTAMPTZ',
    jobs:          'JSON[]'
}"""

EXTRACT = f"""
CREATE OR REPLACE TEMP TABLE today AS
SELECT
    envelope.snapshot_date,
    envelope.fetched_at,
    envelope.ats,
    envelope.company_name,
    envelope.company_token,
    envelope.segment,
    json_extract_string(job, '$.id')                                   AS posting_id,
    envelope.company_token || ':' || json_extract_string(job, '$.id')  AS posting_key,
    md5(cast(job as varchar))                                          AS payload_hash,
    job                                                                AS payload
FROM read_json(?, columns = {ENVELOPE_COLUMNS}) AS envelope,
     UNNEST(envelope.jobs) AS unnested(job)
"""


def existing_payload_keys(con: duckdb.DuckDBPyConnection, snapshot_date: str) -> None:
    """Materialize the payloads already in the store as a temp table.

    Three things here are load-bearing, each of which broke a real run:

    1. The date being persisted is excluded from its own "already known" set.
       Re-running a date rewrites its payload file, so treating that file as
       prior knowledge would find zero new payloads and erase it.

    2. A TEMP TABLE, not a view. A view stays lazy, so the parquet files would
       still be open for reading when COPY starts overwriting one of them.
       Materializing forces the read to finish first.

    3. The file list goes through the relation API rather than a bound
       parameter — DuckDB rejects prepared parameters inside CREATE statements.
    """
    others = sorted(p for p in PAYLOAD_DIR.glob("*.parquet") if p.stem != snapshot_date)

    if not others:
        con.execute(
            "CREATE OR REPLACE TEMP TABLE known "
            "(posting_key VARCHAR, payload_hash VARCHAR)"
        )
        return

    con.read_parquet([p.as_posix() for p in others]).create_view("known_src", replace=True)
    con.execute(
        "CREATE OR REPLACE TEMP TABLE known AS "
        "SELECT DISTINCT posting_key, payload_hash FROM known_src"
    )


def persist_date(con: duckdb.DuckDBPyConnection, snapshot_date: str) -> tuple[int, int]:
    raw_glob = str(RAW_DIR / snapshot_date / "*.json")
    con.execute(EXTRACT, [raw_glob])
    existing_payload_keys(con, snapshot_date)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    PAYLOAD_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_path = SNAPSHOT_DIR / f"{snapshot_date}.parquet"
    con.execute(
        """
        COPY (
            SELECT snapshot_date, fetched_at, ats, company_name, company_token,
                   segment, posting_id, posting_key, payload_hash
            FROM today
            ORDER BY company_token, posting_id
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(snapshot_path)],
    )

    payload_path = PAYLOAD_DIR / f"{snapshot_date}.parquet"
    con.execute(
        """
        COPY (
            SELECT DISTINCT ON (posting_key, payload_hash)
                   posting_key,
                   payload_hash,
                   snapshot_date AS first_seen_date,
                   payload
            FROM today
            WHERE NOT EXISTS (
                SELECT 1 FROM known
                WHERE known.posting_key  = today.posting_key
                  AND known.payload_hash = today.payload_hash
            )
            ORDER BY posting_key, payload_hash
        ) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)
        """,
        [str(payload_path)],
    )

    (snapshot_rows,) = con.execute("SELECT count(*) FROM today").fetchone()
    (new_payloads,) = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [str(payload_path)]
    ).fetchone()

    # An all-zero payload file is just noise in the diff once the store warms up.
    if new_payloads == 0:
        payload_path.unlink()

    return snapshot_rows, new_payloads


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="snapshot date to persist (default: all unpersisted)")
    args = parser.parse_args()

    if not RAW_DIR.exists():
        print("No raw snapshots found — run `python -m ingest.run` first.", file=sys.stderr)
        return 1

    available = sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir())
    dates = [args.date] if args.date else available
    if not dates:
        print("Nothing to persist.", file=sys.stderr)
        return 1

    con = duckdb.connect()
    for snapshot_date in dates:
        rows, payloads = persist_date(con, snapshot_date)
        print(f"  {snapshot_date}  {rows:>6,} postings  |  {payloads:>5,} new payloads")

    snap_mb = sum(p.stat().st_size for p in SNAPSHOT_DIR.glob("*.parquet")) / 1_048_576
    pay_mb = sum(p.stat().st_size for p in PAYLOAD_DIR.glob("*.parquet")) / 1_048_576
    print(f"\nstore/snapshots  {snap_mb:6.1f} MB")
    print(f"store/payloads   {pay_mb:6.1f} MB")
    print(f"store total      {snap_mb + pay_mb:6.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
