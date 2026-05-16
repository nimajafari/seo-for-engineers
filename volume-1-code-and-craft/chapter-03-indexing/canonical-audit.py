#!/usr/bin/env python3
"""
canonical-audit.py

Audit canonical tags on a list of URLs and flag the failure modes
described in Chapter 3 of SEO for Engineers, Volume 1.

For each URL the script:
  1. Fetches the page.
  2. Parses every <link rel="canonical"> element.
  3. Flags missing tags, multiple tags, relative URLs, canonicals built
     from the request URL (containing tracking parameters), cross-host
     canonicals, and self-canonical mismatches.

Usage:
    python canonical-audit.py https://example.com/page
    python canonical-audit.py --urls urls.txt --csv report.csv

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 3.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, parse_qsl, urlunparse

import requests
from bs4 import BeautifulSoup

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

REQUEST_TIMEOUT_SECONDS = 20

# Query parameters that signal tracking, not page identity. A canonical
# URL containing any of these is almost always built from the request URL
# and should be treated as a bug.
TRACKING_PARAMETER_PREFIXES = (
    "utm_",
)

TRACKING_PARAMETER_NAMES = frozenset(
    {
        "fbclid",
        "gclid",
        "gclsrc",
        "dclid",
        "msclkid",
        "mc_cid",
        "mc_eid",
        "ref",
        "session_id",
        "sessionid",
        "sid",
        "_ga",
        "_gl",
        "yclid",
        "scid",
    }
)


@dataclass
class CanonicalAuditResult:
    """Per-URL audit output."""

    url: str
    fetched: bool = False
    status_code: int | None = None
    canonical_count: int = 0
    canonical_href: str | None = None
    issues: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def is_clean(self) -> bool:
        return self.error is None and not self.issues


def is_tracking_parameter(name: str) -> bool:
    """Return True if a query parameter name looks like tracking."""
    lower = name.lower()
    if lower in TRACKING_PARAMETER_NAMES:
        return True
    return any(lower.startswith(prefix) for prefix in TRACKING_PARAMETER_PREFIXES)


def normalize_url(url: str) -> str:
    """Lowercase the scheme and host, strip a trailing slash on the path."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    host = parsed.netloc.lower()
    path = parsed.path
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return urlunparse((scheme, host, path, parsed.params, parsed.query, ""))


def find_tracking_params_in_url(url: str) -> list[str]:
    """Return the list of tracking parameter names present in the URL."""
    parsed = urlparse(url)
    params = parse_qsl(parsed.query, keep_blank_values=True)
    return [name for name, _ in params if is_tracking_parameter(name)]


def audit_url(url: str) -> CanonicalAuditResult:
    """Audit a single URL and return the result."""
    result = CanonicalAuditResult(url=url)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except Exception as exc:
        result.error = f"request failed: {exc}"
        return result

    result.fetched = True
    result.status_code = response.status_code

    if response.status_code >= 400:
        result.issues.append(f"non-success status {response.status_code}")
        return result

    soup = BeautifulSoup(response.text, "html.parser")
    canonical_links = soup.find_all("link", rel=lambda r: r and "canonical" in r)
    result.canonical_count = len(canonical_links)

    if result.canonical_count == 0:
        result.issues.append("missing canonical tag")
        return result

    if result.canonical_count > 1:
        result.issues.append(f"multiple canonical tags ({result.canonical_count})")

    canonical_href = canonical_links[0].get("href") or ""
    canonical_href = canonical_href.strip()
    result.canonical_href = canonical_href

    if not canonical_href:
        result.issues.append("canonical href is empty")
        return result

    parsed_canonical = urlparse(canonical_href)
    if not parsed_canonical.scheme or not parsed_canonical.netloc:
        result.issues.append("canonical href is not absolute")

    tracking_in_canonical = find_tracking_params_in_url(canonical_href)
    if tracking_in_canonical:
        result.issues.append(
            "canonical contains tracking parameters: "
            + ", ".join(sorted(set(tracking_in_canonical)))
        )

    # Cross-host canonical, often legitimate for syndicated content but worth
    # surfacing for manual review.
    final_url = response.url
    parsed_page = urlparse(final_url)
    if (
        parsed_canonical.netloc
        and parsed_page.netloc
        and parsed_canonical.netloc.lower() != parsed_page.netloc.lower()
    ):
        result.issues.append(
            f"canonical points to a different host ({parsed_canonical.netloc})"
        )

    # Self-canonical mismatch. Compare the page's resolved URL to the
    # canonical, after a light normalization that ignores trailing slashes
    # and scheme/host case.
    if (
        parsed_canonical.scheme
        and parsed_canonical.netloc
        and normalize_url(canonical_href) != normalize_url(final_url)
    ):
        result.issues.append(
            "page URL does not match canonical (page may be a duplicate)"
        )

    return result


def load_urls(path: Path) -> list[str]:
    """Read URLs from a text file. One per line. Lines starting with # are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def write_csv(results: Iterable[CanonicalAuditResult], path: Path) -> None:
    """Write audit results to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "url",
                "status_code",
                "canonical_count",
                "canonical_href",
                "is_clean",
                "issues",
                "error",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.url,
                    r.status_code if r.status_code is not None else "",
                    r.canonical_count,
                    r.canonical_href or "",
                    "yes" if r.is_clean else "no",
                    "; ".join(r.issues),
                    r.error or "",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="A single URL to audit.")
    parser.add_argument(
        "--urls",
        help="Path to a text file with one URL per line. Lines starting "
        "with # are ignored.",
    )
    parser.add_argument(
        "--csv",
        help="Write results to this CSV path. Required for batch mode.",
    )
    args = parser.parse_args()

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

    results: list[CanonicalAuditResult] = []
    for url in urls:
        result = audit_url(url)
        results.append(result)
        if args.csv:
            tag = "OK" if result.is_clean else "FLAG"
            issues = "; ".join(result.issues) if result.issues else result.error or ""
            print(f"{tag}\t{result.url}\t{issues}", file=sys.stderr)

    if args.csv:
        write_csv(results, Path(args.csv))
        print(f"Wrote {len(results)} rows to {args.csv}")
    else:
        for result in results:
            print(json.dumps(asdict(result), indent=2))

    # Exit non-zero if any URL has issues or errors, so the script can
    # be used in CI pipelines as a gate.
    return 0 if all(r.is_clean for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())