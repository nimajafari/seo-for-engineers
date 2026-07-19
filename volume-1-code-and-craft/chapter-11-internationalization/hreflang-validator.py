#!/usr/bin/env python3
"""
hreflang-validator.py

Validate hreflang annotations in a sitemap (or sitemap index) against
the five rules Chapter 11 of SEO for Engineers, Volume 1, identifies
as non-negotiable.

  1. Bidirectional confirmation. Every declaration A -> B must have a
     corresponding declaration B -> A.
  2. Self-reference. Every URL must include a hreflang annotation
     pointing to itself.
  3. ISO 639-1 / ISO 3166-1 Alpha-2 code format. Every hreflang value
     must match 'x-default' or a 2-letter language code with an
     optional script subtag (e.g. zh-Hant) and an optional region code
     that is either 2-letter (ISO 3166-1) or 3-digit (UN M.49, e.g.
     es-419).
  4. x-default presence. Recommended per cluster. Warning by default,
     promotable to error with --require-x-default.
  5. Live URL verification (optional, with --check-urls). Every URL
     declared in any hreflang annotation must return HTTP 200 without
     a redirect.

Usage:
    python hreflang-validator.py --sitemap sitemap.xml
    python hreflang-validator.py --sitemap https://example.com/sitemap.xml
    python hreflang-validator.py --sitemap <url> --check-urls
    python hreflang-validator.py --sitemap <url> --require-x-default

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 11.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests
from lxml import etree

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"

REQUEST_TIMEOUT_SECONDS = 30
MAX_SITEMAP_INDEX_DEPTH = 3
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# x-default, or a 2-letter ISO 639-1 language with an optional 4-letter
# script subtag (e.g. zh-Hant) and an optional region that is either a
# 2-letter ISO 3166-1 code or a 3-digit UN M.49 code (e.g. es-419). The
# hreflang value is lower-cased before matching, so the pattern is all
# lowercase.
HREFLANG_PATTERN = re.compile(
    r"^(x-default|[a-z]{2}(-[a-z]{4})?(-([a-z]{2}|[0-9]{3}))?)$"
)


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


def parse_sitemap(
    source: str, depth: int = 0
) -> dict[str, dict[str, str]]:
    """
    Parse a sitemap and extract hreflang annotations.

    Returns a mapping from each URL to its declared alternates:
        { "https://example.com/en/page": { "en": "https://...",
                                            "de": "https://..." } }

    Sitemap indexes are followed recursively up to MAX_SITEMAP_INDEX_DEPTH.
    """
    if depth > MAX_SITEMAP_INDEX_DEPTH:
        print(
            f"WARN: sitemap index depth exceeded at {source}, skipping",
            file=sys.stderr,
        )
        return {}

    try:
        content = fetch_sitemap_content(source)
        # Sitemaps come from arbitrary, possibly untrusted URLs. Disable
        # entity resolution and network access so a hostile sitemap cannot
        # mount an XXE or billion-laughs entity-expansion attack.
        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        root = etree.fromstring(content, parser=parser)
    except Exception as exc:
        print(f"WARN: failed to load {source}, {exc}", file=sys.stderr)
        return {}

    hreflang_map: dict[str, dict[str, str]] = defaultdict(dict)

    if root.tag.endswith("sitemapindex"):
        for child in root.findall(f"{{{SITEMAP_NS}}}sitemap"):
            loc = child.find(f"{{{SITEMAP_NS}}}loc")
            if loc is not None and loc.text:
                child_map = parse_sitemap(loc.text.strip(), depth + 1)
                for url, alternates in child_map.items():
                    hreflang_map[url].update(alternates)
        return dict(hreflang_map)

    for url_elem in root.findall(f"{{{SITEMAP_NS}}}url"):
        loc = url_elem.find(f"{{{SITEMAP_NS}}}loc")
        if loc is None or loc.text is None:
            continue
        canonical_url = loc.text.strip()

        for link_elem in url_elem.findall(f"{{{XHTML_NS}}}link"):
            rel = link_elem.get("rel", "")
            hreflang = link_elem.get("hreflang", "").lower().strip()
            href = link_elem.get("href", "").strip()
            if rel == "alternate" and hreflang and href:
                hreflang_map[canonical_url][hreflang] = href

    return dict(hreflang_map)


def validate_bidirectional(
    hreflang_map: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """
    Validate that every hreflang declaration has a corresponding
    return declaration.
    """
    issues: list[dict[str, str]] = []
    for source_url, alternates in hreflang_map.items():
        for lang, target_url in alternates.items():
            if lang == "x-default":
                continue
            if target_url == source_url:
                continue  # self-reference handled separately
            if target_url not in hreflang_map:
                issues.append(
                    {
                        "severity": "error",
                        "rule": "missing_target_entry",
                        "message": (
                            f"{source_url} declares hreflang={lang} -> "
                            f"{target_url}, but {target_url} has no "
                            "hreflang annotations of its own."
                        ),
                    }
                )
                continue
            target_alternates = hreflang_map[target_url]
            return_found = any(
                href == source_url for href in target_alternates.values()
            )
            if not return_found:
                issues.append(
                    {
                        "severity": "error",
                        "rule": "missing_return_link",
                        "message": (
                            f"{source_url} declares hreflang={lang} -> "
                            f"{target_url}, but {target_url} does not "
                            f"link back to {source_url}."
                        ),
                    }
                )
    return issues


def validate_self_reference(
    hreflang_map: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Validate that every URL includes a self-referencing annotation."""
    issues: list[dict[str, str]] = []
    for source_url, alternates in hreflang_map.items():
        if not any(href == source_url for href in alternates.values()):
            issues.append(
                {
                    "severity": "error",
                    "rule": "missing_self_reference",
                    "message": (
                        f"{source_url} does not include a self-referencing "
                        "hreflang annotation."
                    ),
                }
            )
    return issues


def validate_language_codes(
    hreflang_map: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Validate the format of hreflang language and region codes."""
    issues: list[dict[str, str]] = []
    common_confusions = {
        "uk": "Probably meant 'gb' (Great Britain) instead of 'uk' (United Kingdom is gb, uk is sometimes the language code for Ukrainian, but the country code for Ukraine is 'ua').",
        "cn": "Probably meant 'zh' (Chinese language) instead of 'cn' (China country code).",
        "jp": "Probably meant 'ja' (Japanese language) instead of 'jp' (Japan country code).",
        "kr": "Probably meant 'ko' (Korean language) instead of 'kr' (South Korea country code).",
        "gr": "Probably meant 'el' (Greek language) instead of 'gr' (Greece country code).",
        "cz": "Probably meant 'cs' (Czech language) instead of 'cz' (Czechia country code).",
    }
    for source_url, alternates in hreflang_map.items():
        for lang in alternates:
            if not HREFLANG_PATTERN.match(lang):
                issues.append(
                    {
                        "severity": "error",
                        "rule": "invalid_code_format",
                        "message": (
                            f"{source_url} uses hreflang value '{lang}' which "
                            "does not match expected format (x-default, or "
                            "language[-script][-region], e.g. en, en-us, "
                            "zh-Hant, es-419)."
                        ),
                    }
                )
                continue
            # Language portion is the bit before any hyphen
            lang_only = lang.split("-")[0]
            hint = common_confusions.get(lang_only)
            if hint and lang_only != "x-default":
                issues.append(
                    {
                        "severity": "warning",
                        "rule": "likely_wrong_language_code",
                        "message": (
                            f"{source_url} uses hreflang='{lang}'. {hint}"
                        ),
                    }
                )
    return issues


def _build_clusters(
    hreflang_map: dict[str, dict[str, str]],
) -> list[set[str]]:
    """Group URLs into connected components via Union-Find.

    Two URLs are in the same cluster if either declares the other, or
    if a transitive chain of declarations connects them.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for url, alternates in hreflang_map.items():
        parent.setdefault(url, url)
        for href in alternates.values():
            parent.setdefault(href, href)
            union(url, href)

    components: dict[str, set[str]] = defaultdict(set)
    for node in parent:
        components[find(node)].add(node)
    return list(components.values())


def validate_x_default(
    hreflang_map: dict[str, dict[str, str]],
    require: bool = False,
) -> list[dict[str, str]]:
    """Validate x-default presence in each cluster."""
    issues: list[dict[str, str]] = []
    clusters = _build_clusters(hreflang_map)

    severity = "error" if require else "warning"
    for cluster in clusters:
        has_x_default = False
        for url in cluster:
            if url in hreflang_map and "x-default" in hreflang_map[url]:
                has_x_default = True
                break
        if not has_x_default and len(cluster) > 1:
            issues.append(
                {
                    "severity": severity,
                    "rule": "missing_x_default",
                    "message": (
                        f"Cluster of {len(cluster)} URLs (e.g. "
                        f"{sorted(cluster)[0]}) has no x-default declaration. "
                        "x-default is recommended for users whose locale "
                        "matches no declared variant."
                    ),
                }
            )
    return issues


def validate_live_urls(
    hreflang_map: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    """Fetch each declared URL and verify a 200 status without redirect."""
    issues: list[dict[str, str]] = []
    all_urls: set[str] = set()
    for alternates in hreflang_map.values():
        all_urls.update(alternates.values())

    print(
        f"Fetching {len(all_urls)} URLs for live verification...",
        file=sys.stderr,
    )

    for url in sorted(all_urls):
        try:
            response = requests.head(
                url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            )
            # Some origins and CDNs reject HEAD (405) or do not implement
            # it (501). Retry those with a streamed GET so a HEAD-averse
            # server does not masquerade as a broken hreflang URL. The
            # body is never read; the connection is closed immediately.
            if response.status_code in (405, 501):
                response = requests.get(
                    url,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                    stream=True,
                    headers={"User-Agent": USER_AGENT},
                )
                response.close()
        except Exception as exc:
            issues.append(
                {
                    "severity": "error",
                    "rule": "url_fetch_failed",
                    "message": f"Failed to fetch {url}, {exc}",
                }
            )
            continue

        status = response.status_code
        if 300 <= status < 400:
            location = response.headers.get("Location", "(unknown)")
            issues.append(
                {
                    "severity": "error",
                    "rule": "url_redirects",
                    "message": (
                        f"{url} returned {status} redirect to {location}. "
                        "hreflang URLs must serve content directly without "
                        "redirecting."
                    ),
                }
            )
        elif status != 200:
            issues.append(
                {
                    "severity": "error",
                    "rule": "url_non_200",
                    "message": (
                        f"{url} returned HTTP {status}. hreflang URLs must "
                        "return 200."
                    ),
                }
            )
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sitemap",
        required=True,
        help="Sitemap URL or local file path. Sitemap indexes are followed.",
    )
    parser.add_argument(
        "--check-urls",
        action="store_true",
        help="Fetch every declared URL and verify 200 status without redirect.",
    )
    parser.add_argument(
        "--require-x-default",
        action="store_true",
        help="Treat missing x-default as an error rather than a warning.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write the JSON report. Defaults to stdout summary.",
    )
    args = parser.parse_args()

    print(f"Parsing sitemap, {args.sitemap}", file=sys.stderr)
    hreflang_map = parse_sitemap(args.sitemap)
    print(
        f"Parsed {len(hreflang_map)} URLs with hreflang annotations.",
        file=sys.stderr,
    )

    all_issues: list[dict[str, str]] = []
    all_issues.extend(validate_bidirectional(hreflang_map))
    all_issues.extend(validate_self_reference(hreflang_map))
    all_issues.extend(validate_language_codes(hreflang_map))
    all_issues.extend(
        validate_x_default(hreflang_map, require=args.require_x_default)
    )
    if args.check_urls:
        all_issues.extend(validate_live_urls(hreflang_map))

    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]

    report: dict[str, Any] = {
        "sitemap": args.sitemap,
        "urls_with_hreflang": len(hreflang_map),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": all_issues,
    }

    output_text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)

    # Console summary
    print(
        f"\nResult, {len(errors)} errors, {len(warnings)} warnings.",
        file=sys.stderr,
    )
    for issue in all_issues[:30]:
        prefix = "ERROR" if issue["severity"] == "error" else "WARN "
        print(f"  {prefix} {issue['rule']}, {issue['message']}", file=sys.stderr)
    if len(all_issues) > 30:
        print(
            f"  ... and {len(all_issues) - 30} more (see JSON report).",
            file=sys.stderr,
        )

    if not args.output:
        print(output_text)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())