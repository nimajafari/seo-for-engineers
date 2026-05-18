#!/usr/bin/env python3
"""
gsc-index-coverage.py

Fetch Google Search Console URL Inspection results for one or more
URLs and emit them as JSON. Useful for ongoing production monitoring
of head-management correctness: the inspection response reflects what
Google's last crawl actually saw for each URL, including the indexing
verdict, robots state, canonical Google selected, and last crawl
timestamp.

Designed to be wired into an observability pipeline. A daily cron
that pipes the JSON output into your metrics backend gives you a
leading indicator of indexing-state changes (drops, drift, sudden
spikes in "Discovered, currently not indexed") before they show up
as traffic loss.

Setup:
    pip install google-api-python-client google-auth

    Create a Google Cloud service account, grant it access to your
    Search Console property, download the JSON key, and either pass
    the path with --service-account or set GOOGLE_APPLICATION_CREDENTIALS.

    The Search Console property is identified by its `siteUrl` (e.g.
    'https://www.example.com/' or 'sc-domain:example.com').

Usage:
    # Inspect a single URL
    python gsc-index-coverage.py \\
        --site https://www.example.com/ \\
        --url  https://www.example.com/products/sample

    # Inspect a list of URLs from a file
    python gsc-index-coverage.py \\
        --site https://www.example.com/ \\
        --urls-file urls.txt \\
        --output coverage.json

    # Service-account key path is read from GOOGLE_APPLICATION_CREDENTIALS
    # by default; override with --service-account.

Notes:
    - This script uses the URL Inspection API, which has a quota of
      ~2000 inspections per day per property. Cron loops over large
      URL sets need to respect that quota.
    - The output is one JSON object per URL, written to stdout or to
      --output as a JSON array.

Reference: SEO for Engineers, Volume 1, Chapter 8.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except ImportError:
    print(
        "FATAL: this script requires google-api-python-client and "
        "google-auth. Install with:\n"
        "    pip install google-api-python-client google-auth",
        file=sys.stderr,
    )
    sys.exit(2)

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def load_credentials(key_path: str) -> service_account.Credentials:
    return service_account.Credentials.from_service_account_file(
        key_path, scopes=SCOPES
    )


def load_urls(args: argparse.Namespace) -> list[str]:
    if args.url:
        return [args.url]
    lines = Path(args.urls_file).read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def inspect_one(service, site_url: str, url: str) -> dict[str, Any]:
    """Call urlInspection().index().inspect for one URL and flatten
    the response into a small reporting dict."""
    response = (
        service.urlInspection()
        .index()
        .inspect(body={"inspectionUrl": url, "siteUrl": site_url})
        .execute()
    )
    inspection = response.get("inspectionResult", {})
    indexing = inspection.get("indexStatusResult", {})
    return {
        "url": url,
        "verdict": indexing.get("verdict"),
        "coverage_state": indexing.get("coverageState"),
        "robots_txt_state": indexing.get("robotsTxtState"),
        "indexing_state": indexing.get("indexingState"),
        "google_canonical": indexing.get("googleCanonical"),
        "user_canonical": indexing.get("userCanonical"),
        "last_crawl_time": indexing.get("lastCrawlTime"),
        "page_fetch_state": indexing.get("pageFetchState"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--site",
        required=True,
        help="Search Console property siteUrl, "
        "e.g. https://www.example.com/ or sc-domain:example.com",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single URL to inspect.")
    source.add_argument(
        "--urls-file",
        help="Path to a newline-separated file of URLs to inspect.",
    )
    parser.add_argument(
        "--service-account",
        default=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        help="Path to the service-account JSON key. Defaults to the "
        "GOOGLE_APPLICATION_CREDENTIALS environment variable.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON array to. Defaults to stdout.",
    )
    args = parser.parse_args()

    if not args.service_account:
        print(
            "FATAL: pass --service-account <path> or set "
            "GOOGLE_APPLICATION_CREDENTIALS to a service-account key.",
            file=sys.stderr,
        )
        return 2

    credentials = load_credentials(args.service_account)
    service = build("searchconsole", "v1", credentials=credentials)

    urls = load_urls(args)
    print(f"Inspecting {len(urls)} URL(s) via GSC URL Inspection API...", file=sys.stderr)

    results: list[dict[str, Any]] = []
    errors = 0
    for url in urls:
        try:
            results.append(inspect_one(service, args.site, url))
            print(
                f"  OK  {url} -> verdict={results[-1]['verdict']}",
                file=sys.stderr,
            )
        except Exception as exc:
            errors += 1
            results.append({"url": url, "error": str(exc)})
            print(f"  ERR {url} -> {exc}", file=sys.stderr)

    output = json.dumps(results, indent=2)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Wrote {len(results)} record(s) to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
