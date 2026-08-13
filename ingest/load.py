"""Load raw JSON snapshots into the DuckDB `raw` schema.

One row per posting per snapshot. The full API response for each posting is
kept intact in a JSON column — Greenhouse and Ashby disagree about almost every
field name, and reconciling them is dbt's job, not the loader's. The only thing
pulled out here is the posting id, because reloads need a natural key.

Loads are idempotent per snapshot date: a date is deleted and rewritten, so
re-running after a partial failure is always safe.
"""

from __future__ import annotations

import argparse
import sys

import duckdb

from ingest.config import RAW_DIR, WAREHOUSE

# Declaring the schema explicitly (rather than letting DuckDB sniff it) keeps
# `jobs` as an opaque JSON array. Auto-detection would try to unify Greenhouse
# and Ashby posting shapes into one struct and drop whatever didn't fit.
ENVELOPE_COLUMNS = """{
    company_name:  'VARCHAR',
    company_token: 'VARCHAR',
    ats:           'VARCHAR',
    segment:       'VARCHAR',
    snapshot_date: 'DATE',
    fetched_at:    'TIMESTAMPTZ',
    jobs:          'JSON[]'
}"""

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.postings (
    snapshot_date DATE        NOT NULL,
    fetched_at    TIMESTAMPTZ NOT NULL,
    ats           VARCHAR     NOT NULL,
    company_name  VARCHAR     NOT NULL,
    company_token VARCHAR     NOT NULL,
    segment       VARCHAR,
    posting_id    VARCHAR     NOT NULL,
    payload       JSON        NOT NULL
);
"""

INSERT = f"""
INSERT INTO raw.postings
SELECT
    envelope.snapshot_date,
    envelope.fetched_at,
    envelope.ats,
    envelope.company_name,
    envelope.company_token,
    envelope.segment,
    json_extract_string(job, '$.id') AS posting_id,
    job                              AS payload
FROM read_json(?, columns = {ENVELOPE_COLUMNS}) AS envelope,
     UNNEST(envelope.jobs) AS unnested(job)
"""


def snapshot_dates() -> list[str]:
    if not RAW_DIR.exists():
        return []
    return sorted(p.name for p in RAW_DIR.iterdir() if p.is_dir())


def load_date(con: duckdb.DuckDBPyConnection, snapshot_date: str) -> int:
    pattern = str(RAW_DIR / snapshot_date / "*.json")

    con.execute("DELETE FROM raw.postings WHERE snapshot_date = ?", [snapshot_date])
    con.execute(INSERT, [pattern])

    (count,) = con.execute(
        "SELECT count(*) FROM raw.postings WHERE snapshot_date = ?", [snapshot_date]
    ).fetchone()
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="load only this snapshot date (default: all)")
    args = parser.parse_args()

    dates = [args.date] if args.date else snapshot_dates()
    if not dates:
        print("No snapshots found — run `python -m ingest.run` first.", file=sys.stderr)
        return 1

    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute(DDL)

    for snapshot_date in dates:
        count = load_date(con, snapshot_date)
        print(f"  {snapshot_date}  {count:>6,} postings")

    summary = con.execute("""
        SELECT count(*)                    AS rows,
               count(DISTINCT posting_id)  AS postings,
               count(DISTINCT company_token) AS companies,
               count(DISTINCT snapshot_date) AS snapshots
        FROM raw.postings
    """).fetchone()
    con.close()

    print(
        f"\nraw.postings: {summary[0]:,} rows | {summary[1]:,} distinct postings "
        f"| {summary[2]} companies | {summary[3]} snapshot(s)"
    )
    print(f"Warehouse: {WAREHOUSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
