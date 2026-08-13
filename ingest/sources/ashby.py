"""Ashby public job board API.

Docs: https://developers.ashbyhq.com/reference/introduction
Compensation is opt-in per company; when a company publishes it we get salary
bands directly, which is rare and valuable.
"""

from __future__ import annotations

import httpx

from ingest.config import Company

ENDPOINT = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch(client: httpx.Client, company: Company) -> list[dict]:
    response = client.get(
        ENDPOINT.format(token=company.token),
        params={"includeCompensation": "true"},
    )
    response.raise_for_status()
    return response.json().get("jobs", [])
