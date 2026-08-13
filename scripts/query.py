"""Ad-hoc SQL against the warehouse.

    uv run python scripts/query.py --tables
    uv run python scripts/query.py --describe dim_posting
    uv run python scripts/query.py "select job_family, count(*) from marts.dim_posting group by 1"
    uv run python scripts/query.py --file analysis/skills.sql
    uv run python scripts/query.py "select * from marts.dim_company" --csv out.csv

Opens read-only, so a stray UPDATE can never damage the warehouse and this can
safely run while `dbt build` holds the file.

The stdout reconfigure is not decoration: Windows consoles default to cp1252,
which raises UnicodeEncodeError the moment a job title contains an em dash or
DuckDB draws a box-drawing character.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

sys.stdout.reconfigure(encoding="utf-8")

# Resolved from this file rather than imported from ingest.config, so the
# script works when run directly (`python scripts/query.py`) — running a file
# puts scripts/ on sys.path, not the repo root, so `import ingest` would fail.
WAREHOUSE = Path(__file__).resolve().parent.parent / "data" / "warehouse.duckdb"

LIST_TABLES = """
select schema_name    as schema,
       table_name     as name,
       estimated_size as approx_rows,
       column_count   as cols
from duckdb_tables()
order by schema_name, table_name
"""


def render(result: duckdb.DuckDBPyRelation, limit: int) -> None:
    columns = result.columns
    rows = result.fetchmany(limit)
    if not rows:
        print("(no rows)")
        return

    widths = [
        min(max(len(str(c)), *(len(str(r[i])) for r in rows)), 60)
        for i, c in enumerate(columns)
    ]

    def line(values: list) -> str:
        cells = []
        for value, width in zip(values, widths, strict=True):
            text = "" if value is None else str(value)
            text = text if len(text) <= width else text[: width - 1] + "…"
            cells.append(text.ljust(width))
        return "  ".join(cells).rstrip()

    print(line(list(columns)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(line(list(row)))

    if len(rows) == limit:
        print(f"\n(stopped at {limit} rows — raise with --limit)")
    else:
        print(f"\n{len(rows)} row(s)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sql", nargs="?", help="SQL to run")
    parser.add_argument("--file", help="read SQL from a file instead")
    parser.add_argument("--tables", action="store_true", help="list every table")
    parser.add_argument("--describe", metavar="TABLE", help="show a table's columns")
    parser.add_argument("--csv", metavar="PATH", help="write results to CSV instead of printing")
    parser.add_argument("--limit", type=int, default=50, help="max rows to print (default 50)")
    args = parser.parse_args()

    if not WAREHOUSE.exists():
        print(f"No warehouse at {WAREHOUSE} — run `python -m ingest.load`.", file=sys.stderr)
        return 1

    if args.tables:
        sql = LIST_TABLES
    elif args.describe:
        sql = f"describe {args.describe}"
    elif args.file:
        sql = Path(args.file).read_text(encoding="utf-8")
    elif args.sql:
        sql = args.sql
    else:
        parser.print_help()
        return 1

    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        result = con.sql(sql)
    except duckdb.Error as exc:
        print(f"SQL error: {exc}", file=sys.stderr)
        return 1

    if args.csv:
        con.execute(
            "COPY (" + sql.rstrip().rstrip(";") + ") TO ? (HEADER, DELIMITER ',')",
            [args.csv],
        )
        print(f"Wrote {args.csv}")
    else:
        render(result, args.limit)

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
