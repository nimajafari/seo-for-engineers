#!/usr/bin/env python3
"""
url-design-linter.py

Validate a population of URLs against the URL design rules Chapter
12 of SEO for Engineers, Volume 1, establishes as engineering
standards.

Checks performed against every URL.

  1. Case. Path must be lowercase.
  2. Trailing slash. Must match the configured convention.
  3. Insignificant query parameters. Tracking, session, and display
     parameters must not appear in canonical URLs.
  4. Reserved slugs. Path segments matching reserved keywords are
     flagged.
  5. URL length. URLs over the configured threshold are flagged.
  6. Encoded character density. URLs with a high percentage of
     percent-encoded characters are flagged.
  7. Deep nesting. URLs over the configured path-depth threshold
     are flagged.

Usage:
    python url-design-linter.py --sitemap <url>
    python url-design-linter.py --urls urls.txt
    python url-design-linter.py --sitemap <url> --trailing-slash require
    python url-design-linter.py --sitemap <url> --output report.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

import requests
from lxml import etree

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

REQUEST_TIMEOUT_SECONDS = 30
MAX_SITEMAP_INDEX_DEPTH = 3
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

DEFAULT_MAX_LENGTH = 2048
DEFAULT_MAX_DEPTH = 8
DEFAULT_ENCODED_DENSITY_THRESHOLD = 0.20  # 20% percent-encoded chars

# Default insignificant query parameters, from the chapter's
# INSIGNIFICANT_PARAMS set.
DEFAULT_INSIGNIFICANT_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "fbclid", "gclid", "msclkid", "ref",
    "sessionid", "sid", "source", "mc_cid", "mc_eid",
    "sort", "order", "view", "display",
})

DEFAULT_RESERVED_SLUGS = frozenset({
    "admin", "api", "static", "assets", "login", "logout", "register",
    "search", "feed", "sitemap", "robots", "favicon", "null",
    "undefined", "new", "edit", "delete", "settings", "profile",
    "account", "help", "support", "about", "contact", "privacy",
    "terms", "status", "health", "metrics",
})


def fetch_sitemap_content(source: str) -> bytes:
    """Fetch a sitemap from a URL or read from a local path."""
    if source.startswith(("http://", "https://")):
        response = requests.get(
            source,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        return response.content
    return Path(source).read_bytes()


def parse_sitemap_urls(source: str, depth: int = 0) -> list[str]:
    """Parse a sitemap (or sitemap index) and return the URL list."""
    if depth > MAX_SITEMAP_INDEX_DEPTH:
        print(
            f"WARN: sitemap index depth exceeded at {source}",
            file=sys.stderr,
        )
        return []

    try:
        content = fetch_sitemap_content(source)
        root = etree.fromstring(content)
    except Exception as exc:
        print(f"WARN: failed to load {source}, {exc}", file=sys.stderr)
        return []

    urls: list[str] = []

    if root.tag.endswith("sitemapindex"):
        for child in root.findall(f"{{{SITEMAP_NS}}}sitemap"):
            loc = child.find(f"{{{SITEMAP_NS}}}loc")
            if loc is not None and loc.text:
                urls.extend(parse_sitemap_urls(loc.text.strip(), depth + 1))
        return urls

    for url_elem in root.findall(f"{{{SITEMAP_NS}}}url"):
        loc = url_elem.find(f"{{{SITEMAP_NS}}}loc")
        if loc is not None and loc.text:
            urls.append(loc.text.strip())

    return urls


def load_urls(args: argparse.Namespace) -> list[str]:
    """Load URLs from a sitemap or file, depending on arguments."""
    if args.sitemap:
        return parse_sitemap_urls(args.sitemap)
    if args.urls:
        return [
            line.strip()
            for line in Path(args.urls).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    return []


def check_case(url: str, parsed) -> list[dict[str, str]]:
    """Path must be lowercase. Query string values may be case-sensitive."""
    issues = []
    path = parsed.path
    if path != path.lower():
        issues.append({
            "severity": "error",
            "rule": "mixed_case_path",
            "message": (
                f"Path contains uppercase characters, {path}. Mixed case "
                "creates duplicate-content variants on case-sensitive "
                "filesystems."
            ),
        })
    return issues


def check_trailing_slash(
    url: str, parsed, convention: str
) -> list[dict[str, str]]:
    """Path must match the configured trailing-slash convention."""
    issues = []
    path = parsed.path
    if path == "/" or path == "":
        return issues  # Root is always allowed to have trailing slash

    has_trailing = path.endswith("/")
    if convention == "require" and not has_trailing:
        issues.append({
            "severity": "error",
            "rule": "missing_trailing_slash",
            "message": (
                f"URL {url} lacks a trailing slash, but the convention "
                "requires one."
            ),
        })
    elif convention == "forbid" and has_trailing:
        issues.append({
            "severity": "error",
            "rule": "unwanted_trailing_slash",
            "message": (
                f"URL {url} has a trailing slash, but the convention "
                "forbids one."
            ),
        })
    return issues


def check_insignificant_params(
    url: str, parsed, insignificant: frozenset
) -> list[dict[str, str]]:
    """Tracking and display parameters must not appear in canonical URLs."""
    issues = []
    if not parsed.query:
        return issues
    params = parse_qs(parsed.query, keep_blank_values=True)
    found = [k for k in params if k.lower() in insignificant]
    if found:
        issues.append({
            "severity": "error",
            "rule": "insignificant_params_in_canonical",
            "message": (
                f"URL {url} contains insignificant query parameters: "
                f"{', '.join(found)}. These should be stripped from "
                "canonical URLs, sitemap entries, and internal links."
            ),
        })
    return issues


def check_reserved_slugs(
    url: str, parsed, reserved: frozenset
) -> list[dict[str, str]]:
    """Path segments matching reserved keywords are likely routing collisions."""
    issues = []
    segments = [s for s in parsed.path.split("/") if s]
    for seg in segments:
        # Strip any trailing extension before comparison.
        base = seg.split(".")[0].lower()
        if base in reserved:
            issues.append({
                "severity": "warning",
                "rule": "reserved_slug_in_path",
                "message": (
                    f"URL {url} contains path segment '{seg}' which matches "
                    "a reserved keyword. This may collide with application "
                    "routes."
                ),
            })
    return issues


def check_length(url: str, max_length: int) -> list[dict[str, str]]:
    """URLs over the configured length threshold are flagged."""
    issues = []
    if len(url) > max_length:
        issues.append({
            "severity": "warning",
            "rule": "url_too_long",
            "message": (
                f"URL is {len(url)} characters, exceeding the threshold of "
                f"{max_length}. Long URLs are harder to share, more likely "
                "to be truncated by some clients, and often indicate that "
                "the URL is encoding too much information."
            ),
        })
    return issues


def check_encoded_density(
    url: str, threshold: float
) -> list[dict[str, str]]:
    """High percent-encoding density suggests a slug-generation bug."""
    issues = []
    if "%" not in url:
        return issues
    encoded_chars = url.count("%") * 3  # Each %XX is 3 chars
    density = encoded_chars / len(url) if len(url) > 0 else 0
    if density > threshold:
        issues.append({
            "severity": "warning",
            "rule": "high_encoded_density",
            "message": (
                f"URL {url} is {density:.0%} percent-encoded characters. "
                "High encoding density often indicates that slug "
                "generation is preserving characters that should be "
                "transliterated or stripped."
            ),
        })
    return issues


def check_depth(
    url: str, parsed, max_depth: int
) -> list[dict[str, str]]:
    """Deep paths are fragile, taxonomy changes break them."""
    issues = []
    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) > max_depth:
        issues.append({
            "severity": "warning",
            "rule": "deep_path_nesting",
            "message": (
                f"URL has {len(segments)} path segments. Deep nesting "
                "creates fragile URLs that break when the hierarchy is "
                "reorganized."
            ),
        })
    return issues


def lint_url(
    url: str,
    trailing_slash: str,
    max_length: int,
    max_depth: int,
    encoded_density_threshold: float,
    insignificant: frozenset,
    reserved: frozenset,
) -> list[dict[str, str]]:
    """Run all checks against a single URL."""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        return [{
            "severity": "error",
            "rule": "parse_failed",
            "message": f"URL {url} could not be parsed, {exc}",
        }]

    issues: list[dict[str, str]] = []
    issues.extend(check_case(url, parsed))
    issues.extend(check_trailing_slash(url, parsed, trailing_slash))
    issues.extend(check_insignificant_params(url, parsed, insignificant))
    issues.extend(check_reserved_slugs(url, parsed, reserved))
    issues.extend(check_length(url, max_length))
    issues.extend(check_encoded_density(url, encoded_density_threshold))
    issues.extend(check_depth(url, parsed, max_depth))

    # Attach the URL to every issue for the report.
    for issue in issues:
        issue["url"] = url

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sitemap",
        help="Sitemap URL or local file path. Sitemap indexes are followed.",
    )
    parser.add_argument(
        "--urls",
        help="Path to a file containing one URL per line.",
    )
    parser.add_argument(
        "--trailing-slash",
        default="forbid",
        choices=["require", "forbid", "skip"],
        help="Trailing slash convention. Default, forbid.",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=DEFAULT_MAX_LENGTH,
        help=f"Maximum URL length. Default, {DEFAULT_MAX_LENGTH}.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=DEFAULT_MAX_DEPTH,
        help=f"Maximum path-segment depth. Default, {DEFAULT_MAX_DEPTH}.",
    )
    parser.add_argument(
        "--encoded-density",
        type=float,
        default=DEFAULT_ENCODED_DENSITY_THRESHOLD,
        help=(
            "Percent-encoded character density threshold (0.0 to 1.0). "
            f"Default, {DEFAULT_ENCODED_DENSITY_THRESHOLD}."
        ),
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    args = parser.parse_args()

    if not args.sitemap and not args.urls:
        parser.error("Must provide --sitemap or --urls.")

    urls = load_urls(args)
    print(f"Loaded {len(urls)} URLs for linting.", file=sys.stderr)

    all_issues: list[dict[str, str]] = []
    for url in urls:
        all_issues.extend(lint_url(
            url,
            trailing_slash=args.trailing_slash,
            max_length=args.max_length,
            max_depth=args.max_depth,
            encoded_density_threshold=args.encoded_density,
            insignificant=DEFAULT_INSIGNIFICANT_PARAMS,
            reserved=DEFAULT_RESERVED_SLUGS,
        ))

    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]

    # Group rule counts for the summary.
    rule_counts: dict[str, int] = defaultdict(int)
    for issue in all_issues:
        rule_counts[issue["rule"]] += 1

    report: dict[str, Any] = {
        "urls_checked": len(urls),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues_by_rule": dict(rule_counts),
        "issues": all_issues,
    }

    output_text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)

    # Console summary.
    print(
        f"\nResult, {len(errors)} errors, {len(warnings)} warnings "
        f"across {len(urls)} URLs.",
        file=sys.stderr,
    )
    print("By rule:", file=sys.stderr)
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {rule}, {count}", file=sys.stderr)
    if len(all_issues) > 0:
        print("\nFirst issues:", file=sys.stderr)
        for issue in all_issues[:15]:
            prefix = "ERROR" if issue["severity"] == "error" else "WARN "
            print(
                f"  {prefix} {issue['rule']}, {issue.get('url', '')}",
                file=sys.stderr,
            )
        if len(all_issues) > 15:
            print(
                f"  ... and {len(all_issues) - 15} more.",
                file=sys.stderr,
            )

    if not args.output:
        print(output_text)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())