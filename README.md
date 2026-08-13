# job-market-intel

A daily pipeline that tracks the US tech job market: what roles companies are
hiring for, which skills those roles actually ask for, and how that mix shifts
over time.

## Why this exists

Most job-market analysis is a one-off scrape of a single day. That can tell you
what is open right now, but it cannot tell you what is *changing* — which is the
only part that helps you make a decision. This pipeline takes a snapshot every
day and keeps the history, so postings can be tracked from the day they open to
the day they disappear.

## Where the data comes from

Companies that use Greenhouse or Ashby expose their job boards as public JSON
APIs by design — these are the same endpoints that power the "Careers" page on
their own websites, and they return the complete posting text.

That is a deliberate choice over scraping LinkedIn, Indeed, or Glassdoor: those
sites prohibit automated collection in their terms of service and actively block
it. The ATS endpoints are stable, documented, and intended for this use.

Currently tracking **24 companies / ~5,600 open postings**. See
[`companies.yml`](companies.yml).

## Architecture

```
ATS APIs ->  raw JSON      ->  parquet store  ->  DuckDB  ->  dbt  ->  Power BI
(httpx)      data/raw/         store/             raw.*      marts.*
             local only        committed
```

The parquet store is the part worth explaining. CI runners are ephemeral, so
whatever the pipeline must remember between runs has to live in git — but the
raw JSON is ~66 MB per day, which would bloat the repo past a gigabyte in a
month.

Nearly all of that weight is job descriptions, and descriptions rarely change.
So the store splits into a thin daily snapshot (which postings were open) and
an append-only payload table keyed by content hash (what each posting said).
A payload is written once; an edited posting adds a second version rather than
overwriting the first, and the snapshot records which version was live on which
day. That means the warehouse for any past date can be rebuilt exactly.

**66 MB/day becomes ~0.3 MB/day**, and `ingest.load` can rebuild the entire
warehouse from git alone — which is exactly what CI does on every pull request,
with no network access and no API calls.

| Layer | Tool |
|---|---|
| Ingest | Python + httpx |
| Warehouse | DuckDB (single file, no server) |
| Transform | dbt Core |
| Data quality | dbt tests |
| Orchestration | GitHub Actions (cron) |
| Presentation | Power BI |

## Quickstart

```powershell
uv sync                            # create venv, install everything
uv run python -m ingest.run        # fetch every board -> data/raw/
uv run python -m ingest.persist    # raw JSON -> store/ parquet
uv run python -m ingest.load       # store/ -> DuckDB
cd transform; uv run dbt build --profiles-dir .
```

To rebuild from a fresh clone without hitting any API, skip the first two
steps — the store is already in the repo.

## Automation

| Workflow | Trigger | Does |
|---|---|---|
| `ingest.yml` | 06:20 UTC daily | Fetch, persist, rebuild, test, commit the store |
| `ci.yml` | PR and push to main | Lint, rebuild from store, run all dbt tests |

The daily job tests the new snapshot *before* committing it, so a bad day never
lands on main.

## Repo layout

```
ingest/          one module per ATS source
  sources/       greenhouse.py, ashby.py
  run.py         fetch all boards      -> data/raw/
  persist.py     raw JSON              -> store/ parquet
  load.py        store/                -> DuckDB raw schema
transform/       dbt project (staging -> intermediate -> marts)
store/           committed parquet: the pipeline's memory
scripts/         utilities, e.g. probing new ATS boards
data/            raw JSON + warehouse.duckdb (both gitignored)
```
