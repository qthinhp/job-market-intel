"""Rebuild the DuckDB warehouse from the committed parquet store.

Reads `store/`, not `data/raw/`. That distinction is the whole point: the store
is in git, so a clean CI runner — which has no raw JSON and never ran the
ingest — can reconstruct the warehouse exactly. Raw JSON stays local as a
debugging artifact.

The rebuild is total rather than incremental. At this size it costs under a
second, and it removes an entire class of bug where a partially applied load
leaves the warehouse in a state no one can reproduce.
"""

from __future__ import annotations

import sys

import duckdb

from ingest.config import WAREHOUSE
from ingest.persist import PAYLOAD_DIR, SNAPSHOT_DIR

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
DROP TABLE IF EXISTS raw.postings;

CREATE TABLE raw.postings (
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

# Snapshots carry the payload_hash that was live on that date, so a posting
# edited mid-flight resolves to the text it actually had at the time.
INSERT = """
INSERT INTO raw.postings
SELECT
    snapshots.snapshot_date,
    snapshots.fetched_at,
    snapshots.ats,
    snapshots.company_name,
    snapshots.company_token,
    snapshots.segment,
    snapshots.posting_id,
    payloads.payload
FROM read_parquet(?) AS snapshots
JOIN read_parquet(?) AS payloads
    ON  snapshots.posting_key  = payloads.posting_key
    AND snapshots.payload_hash = payloads.payload_hash
"""


def main() -> int:
    snapshot_glob = str(SNAPSHOT_DIR / "*.parquet")
    payload_glob = str(PAYLOAD_DIR / "*.parquet")

    if not any(SNAPSHOT_DIR.glob("*.parquet")):
        print("Store is empty — run `python -m ingest.persist` first.", file=sys.stderr)
        return 1

    WAREHOUSE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute(DDL)
    con.execute(INSERT, [snapshot_glob, payload_glob])

    # The join above is inner: a snapshot row whose payload is missing from the
    # store would vanish silently and undercount that day. Catch it here rather
    # than discovering a dip in the dashboard three weeks later.
    (expected,) = con.execute(
        "SELECT count(*) FROM read_parquet(?)", [snapshot_glob]
    ).fetchone()
    (loaded,) = con.execute("SELECT count(*) FROM raw.postings").fetchone()

    if loaded != expected:
        print(
            f"ERROR: {expected - loaded} snapshot rows had no matching payload "
            f"(expected {expected:,}, loaded {loaded:,}). The store is inconsistent.",
            file=sys.stderr,
        )
        return 1

    summary = con.execute("""
        SELECT count(*),
               count(DISTINCT company_token),
               count(DISTINCT snapshot_date),
               min(snapshot_date),
               max(snapshot_date)
        FROM raw.postings
    """).fetchone()
    con.close()

    print(
        f"raw.postings: {summary[0]:,} rows | {summary[1]} companies | "
        f"{summary[2]} snapshot(s) | {summary[3]} .. {summary[4]}"
    )
    print(f"Warehouse: {WAREHOUSE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
