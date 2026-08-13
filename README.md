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
ATS APIs  ->  raw JSON snapshots  ->  DuckDB  ->  dbt  ->  star schema  ->  Power BI
(httpx)       data/raw/{date}/       raw.*      tests     marts.*
```

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
uv sync                          # create venv, install everything
uv run python -m ingest.run      # pull today's snapshot to data/raw/
uv run python -m ingest.load     # load snapshots into DuckDB
cd transform; uv run dbt build   # transform + test
```

## Repo layout

```
ingest/          Python ingest: one module per ATS source
  sources/       greenhouse.py, ashby.py
  run.py         fetch all boards -> data/raw/
  load.py        data/raw/ -> DuckDB raw schema
transform/       dbt project (staging -> marts)
scripts/         one-off utilities, e.g. board probing
data/            raw snapshots + warehouse.duckdb (both gitignored)
```
