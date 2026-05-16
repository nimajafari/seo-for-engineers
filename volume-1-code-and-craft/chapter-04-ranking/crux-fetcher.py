#!/usr/bin/env python3
"""
crux-fetcher.py

Fetch field Core Web Vitals data from the Chrome User Experience Report
(CrUX) API. This is the same data source Google's ranking systems use
for the Page Experience signal.

Output is a CSV with LCP, INP, and CLS values at the 75th percentile,
along with the percentage of visits in the "good", "needs improvement",
and "poor" buckets for each metric.

Requires a Google API key with the CrUX API enabled. Get one from the
Google Cloud Console. Pass via the CRUX_API_KEY environment variable
or the --key flag.

Usage:
    export CRUX_API_KEY=your_api_key_here
    python crux-fetcher.py https://example.com/
    python crux-fetcher.py --urls urls.txt --csv report.csv
    python crux-fetcher.py --urls urls.txt --csv report.csv --form-factor DESKTOP
    python crux-fetcher.py --urls urls.txt --csv report.csv --origin

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 4.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

CRUX_ENDPOINT = "https://chromeuxreport.googleapis.com/v1/records:queryRecord"
REQUEST_TIMEOUT_SECONDS = 20

METRIC_KEYS = (
    "largest_contentful_paint",
    "interaction_to_next_paint",
    "cumulative_layout_shift",
)

METRIC_SHORT_NAMES = {
    "largest_contentful_paint": "lcp",
    "interaction_to_next_paint": "inp",
    "cumulative_layout_shift": "cls",
}


@dataclass
class CruxResult:
    """Per-URL CrUX output."""

    url: str
    has_data: bool = False
    form_factor: str = ""
    # Per-metric p75 values and good/ni/poor percentages.
    metrics: dict[str, dict[str, float | None]] = field(default_factory=dict)
    error: str | None = None


def origin_of(url: str) -> str:
    """Return the origin (scheme + netloc) of a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def query_crux(
    api_key: str,
    target: str,
    form_factor: str | None,
    as_origin: bool,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    """Call the CrUX API for a target URL or origin.

    Returns (has_data, record, error). has_data is False for 404s, which
    mean the target has insufficient traffic for CrUX to report.
    """
    body: dict[str, Any] = {}
    body["origin" if as_origin else "url"] = target
    if form_factor:
        body["formFactor"] = form_factor

    try:
        response = requests.post(
            CRUX_ENDPOINT,
            params={"key": api_key},
            json=body,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return False, None, f"request failed: {exc}"

    if response.status_code == 404:
        return False, None, None

    if response.status_code != 200:
        # Surface the API error so users can fix the request.
        try:
            err = response.json().get("error", {}).get("message", response.text)
        except Exception:
            err = response.text
        return False, None, f"HTTP {response.status_code}: {err}"

    try:
        payload = response.json()
    except Exception as exc:
        return False, None, f"invalid JSON response: {exc}"

    record = payload.get("record")
    if not record:
        return False, None, "response did not contain a record"

    return True, record, None


def extract_metrics(record: dict[str, Any]) -> dict[str, dict[str, float | None]]:
    """Pull p75 values and bucket percentages from a CrUX record."""
    metrics_in = record.get("metrics", {})
    out: dict[str, dict[str, float | None]] = {}
    for key in METRIC_KEYS:
        short = METRIC_SHORT_NAMES[key]
        out[short] = {"p75": None, "good_pct": None, "ni_pct": None, "poor_pct": None}
        metric = metrics_in.get(key)
        if not metric:
            continue
        percentiles = metric.get("percentiles", {})
        p75 = percentiles.get("p75")
        if p75 is not None:
            # CLS comes back as a string in the CrUX response.
            try:
                out[short]["p75"] = float(p75)
            except (TypeError, ValueError):
                out[short]["p75"] = None
        histogram = metric.get("histogram", [])
        # CrUX returns three buckets, good / needs improvement / poor.
        bucket_keys = ("good_pct", "ni_pct", "poor_pct")
        for i, bucket in enumerate(histogram[:3]):
            density = bucket.get("density")
            if density is not None:
                out[short][bucket_keys[i]] = float(density) * 100
    return out


def fetch_one(
    api_key: str,
    url: str,
    form_factor: str | None,
    as_origin: bool,
) -> CruxResult:
    """Fetch CrUX data for a single URL."""
    target = origin_of(url) if as_origin else url
    result = CruxResult(url=url, form_factor=form_factor or "ALL_FORM_FACTORS")

    has_data, record, error = query_crux(
        api_key=api_key,
        target=target,
        form_factor=form_factor,
        as_origin=as_origin,
    )

    if error:
        result.error = error
        return result

    if not has_data:
        return result

    assert record is not None
    result.has_data = True
    result.metrics = extract_metrics(record)
    return result


def load_urls(path: Path) -> list[str]:
    """Read URLs from a text file. One per line. Lines starting with # are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def write_csv(results: Iterable[CruxResult], path: Path) -> None:
    """Write CrUX results to a CSV file."""
    header = ["url", "has_data", "form_factor"]
    for short in METRIC_SHORT_NAMES.values():
        header += [
            f"{short}_p75",
            f"{short}_good_pct",
            f"{short}_ni_pct",
            f"{short}_poor_pct",
        ]
    header.append("error")

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for r in results:
            row: list[Any] = [r.url, "yes" if r.has_data else "no", r.form_factor]
            for short in METRIC_SHORT_NAMES.values():
                m = r.metrics.get(short, {})
                row += [
                    "" if m.get("p75") is None else m["p75"],
                    "" if m.get("good_pct") is None else f"{m['good_pct']:.2f}",
                    "" if m.get("ni_pct") is None else f"{m['ni_pct']:.2f}",
                    "" if m.get("poor_pct") is None else f"{m['poor_pct']:.2f}",
                ]
            row.append(r.error or "")
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="A single URL to fetch.")
    parser.add_argument("--urls", help="Path to a text file with one URL per line.")
    parser.add_argument("--csv", help="Write results to this CSV path. Required for batch mode.")
    parser.add_argument(
        "--key",
        help="CrUX API key. Defaults to the CRUX_API_KEY environment variable.",
    )
    parser.add_argument(
        "--form-factor",
        choices=["PHONE", "DESKTOP", "TABLET"],
        help="Restrict to a specific form factor. Default is all form factors.",
    )
    parser.add_argument(
        "--origin",
        action="store_true",
        help="Query origin-level data instead of URL-level. Use this for "
        "low-traffic URLs that do not have individual CrUX records.",
    )
    args = parser.parse_args()

    api_key = args.key or os.environ.get("CRUX_API_KEY")
    if not api_key:
        print(
            "error: no API key. Pass --key or set CRUX_API_KEY in the environment.",
            file=sys.stderr,
        )
        return 2

    if args.urls and not args.csv:
        print("--urls requires --csv for batch output.", file=sys.stderr)
        return 2

    urls: list[str]
    if args.urls:
        urls = load_urls(Path(args.urls))
    elif args.url:
        urls = [args.url]
    else:
        print("Provide a URL or --urls <file>.", file=sys.stderr)
        return 2

    results: list[CruxResult] = []
    for url in urls:
        result = fetch_one(
            api_key=api_key,
            url=url,
            form_factor=args.form_factor,
            as_origin=args.origin,
        )
        results.append(result)
        if args.csv:
            status = "OK" if result.has_data else ("ERR" if result.error else "NO_DATA")
            msg = result.error or ""
            print(f"{status}\t{result.url}\t{msg}", file=sys.stderr)

    if args.csv:
        write_csv(results, Path(args.csv))
        print(f"wrote {len(results)} rows to {args.csv}")
    else:
        for r in results:
            print(json.dumps(asdict(r), indent=2))

    return 0 if all(r.error is None for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())