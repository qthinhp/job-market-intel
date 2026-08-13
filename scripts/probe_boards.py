"""Check whether candidate ATS board tokens are live, before adding them to
companies.yml.

    uv run python scripts/probe_boards.py stripe figma some-startup

Prints one line per token with the ATS that answered and the posting count.
Companies migrate between ATS vendors fairly often, so this is also how you
re-verify the existing list when the ingest starts logging skips.
"""

from __future__ import annotations

import sys

import httpx

PROBES = {
    "greenhouse": (
        "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
        lambda payload: len(payload["jobs"]),
    ),
    "ashby": (
        "https://api.ashbyhq.com/posting-api/job-board/{token}",
        lambda payload: len(payload.get("jobs", [])),
    ),
    "lever": (
        "https://api.lever.co/v0/postings/{token}?mode=json",
        len,
    ),
}


def probe(client: httpx.Client, token: str) -> None:
    for ats, (url, count) in PROBES.items():
        try:
            response = client.get(url.format(token=token), timeout=15)
            response.raise_for_status()
            n = count(response.json())
        except Exception:  # noqa: BLE001 - a miss is the expected case here
            continue
        if n:
            print(f"OK    {token:<16} ats={ats:<11} jobs={n}")
            return
        print(f"EMPTY {token:<16} ats={ats:<11} (board exists but has 0 postings)")
        return
    print(f"--    {token:<16} no public board found")


def main() -> int:
    tokens = sys.argv[1:]
    if not tokens:
        print(__doc__)
        return 1
    with httpx.Client(headers={"User-Agent": "job-market-intel/0.1"}) as client:
        for token in tokens:
            probe(client, token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
