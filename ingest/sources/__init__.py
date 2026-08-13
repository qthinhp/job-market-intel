"""One module per applicant tracking system.

Each source exposes `fetch(client, company) -> list[dict]` returning postings
exactly as the API gave them. Normalization happens in dbt, not here — raw
stays raw so a modeling mistake never costs us the original data.
"""

from ingest.sources import ashby, greenhouse

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "ashby": ashby.fetch,
}

__all__ = ["FETCHERS", "ashby", "greenhouse"]
