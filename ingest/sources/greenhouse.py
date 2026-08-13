"""Greenhouse public job board API.

Docs: https://developers.greenhouse.io/job-board.html
`content=true` returns the full HTML job description, which is what the skill
extraction step later reads.
"""

from __future__ import annotations

import httpx

from ingest.config import Company

ENDPOINT = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch(client: httpx.Client, company: Company) -> list[dict]:
    response = client.get(
        ENDPOINT.format(token=company.token),
        params={"content": "true"},
    )
    response.raise_for_status()
    return response.json()["jobs"]
