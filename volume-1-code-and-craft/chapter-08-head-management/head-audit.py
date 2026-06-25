#!/usr/bin/env python3
"""
head-audit.py

Audit the contents of the <head> element on one or more pages against
the checklist from Chapter 8 of SEO for Engineers, Volume 1.

For each page, the audit reports findings in three severity buckets.
High severity findings include missing or duplicated title, missing or
duplicated canonical, canonical pointing to a non-200 response, the
noindex plus canonical-to-an-indexable-URL conflict, and noindex on a
URL flagged as indexable. Medium severity findings include relative
canonical URLs, canonical host mismatches, generic title values, and
missing meta description. Low severity findings include missing OG and
X card markup and missing or misconfigured viewport.

URLs can be sourced from --url, --urls-file, or --sitemap.

Usage:
    python head-audit.py --url https://example.com/
    python head-audit.py --urls-file urls.txt
    python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50
    python head-audit.py --url https://example.com/ --check-canonical-status
    python head-audit.py --url https://example.com/account --expect-noindex

URLs flagged as intentionally non-indexable do not raise a noindex
finding. Pass --expect-noindex with --url, or append a 'noindex' token
to a urls-file line:

    https://example.com/account/settings    noindex
    https://example.com/search               noindex

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 8.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from lxml import etree

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# Title values that suggest a CMS or template default rather than a
# real, descriptive title. Case-insensitive exact match.
GENERIC_TITLE_VALUES = {
    "",
    "untitled",
    "home",
    "homepage",
    "page",
    "default",
    "welcome",
    "index",
    "title",
}


@dataclass
class Finding:
    """A single issue found during the audit."""

    severity: str  # "high", "medium", "low"
    rule: str
    message: str
    detail: str | None = None


@dataclass
class PageReport:
    """Aggregate audit output for a single URL."""

    url: str
    fetched: bool = False
    status_code: int | None = None
    error: str | None = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "fetched": self.fetched,
            "status_code": self.status_code,
            "error": self.error,
            "findings": [
                {
                    "severity": f.severity,
                    "rule": f.rule,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
            "counts": {
                "high": sum(1 for f in self.findings if f.severity == "high"),
                "medium": sum(1 for f in self.findings if f.severity == "medium"),
                "low": sum(1 for f in self.findings if f.severity == "low"),
            },
        }


def fetch(url: str) -> tuple[int, str, dict[str, str]]:
    """Fetch a URL and return status code, body, and response headers."""
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    response.raise_for_status()
    # Normalize header names to lowercase.
    headers = {k.lower(): v for k, v in response.headers.items()}
    return response.status_code, response.text, headers


def fetch_status_only(url: str) -> int:
    """HEAD a URL and return the final status code after redirects."""
    response = requests.head(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    return response.status_code


def parse_sitemap(sitemap_url: str, limit: int | None = None) -> list[str]:
    """Parse a sitemap or sitemap index and return up to `limit` URLs."""
    response = requests.get(
        sitemap_url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()

    # Sitemaps come from arbitrary, possibly untrusted URLs. Disable
    # entity resolution and network access so a hostile sitemap cannot
    # mount an XXE or billion-laughs entity-expansion attack.
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, dtd_validation=False
    )
    root = etree.fromstring(response.content, parser=parser)

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    # If this is a sitemap index, recurse into each child sitemap.
    if root.tag.endswith("sitemapindex"):
        urls: list[str] = []
        for child in root.findall("sm:sitemap", ns):
            loc = child.find("sm:loc", ns)
            if loc is not None and loc.text:
                urls.extend(parse_sitemap(loc.text.strip(), limit=limit))
                if limit is not None and len(urls) >= limit:
                    return urls[:limit]
        return urls

    # Otherwise it is a urlset.
    urls = []
    for child in root.findall("sm:url", ns):
        loc = child.find("sm:loc", ns)
        if loc is not None and loc.text:
            urls.append(loc.text.strip())
            if limit is not None and len(urls) >= limit:
                break
    return urls


def get_head_data(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract head element data into a structured dict."""

    def meta_content(name_or_property: str, attr: str = "name") -> str | None:
        tag = soup.find("meta", attrs={attr: name_or_property})
        return tag.get("content") if tag else None

    titles = soup.find_all("title")
    canonical_tags = soup.find_all("link", attrs={"rel": "canonical"})
    description_tags = soup.find_all("meta", attrs={"name": "description"})
    charset_tag = soup.find("meta", charset=True)

    return {
        "title_count": len(titles),
        "title": titles[0].get_text().strip() if titles else None,
        "description": meta_content("description"),
        "description_count": len(description_tags),
        "charset": charset_tag.get("charset") if charset_tag else None,
        "robots": meta_content("robots"),
        "googlebot": meta_content("googlebot"),
        "viewport": meta_content("viewport"),
        "canonical_count": len(canonical_tags),
        "canonical": canonical_tags[0].get("href") if canonical_tags else None,
        "og_title": meta_content("og:title", attr="property"),
        "og_description": meta_content("og:description", attr="property"),
        "og_image": meta_content("og:image", attr="property"),
        "og_url": meta_content("og:url", attr="property"),
        "twitter_card": meta_content("twitter:card"),
    }


def check_title(head: dict[str, Any], report: PageReport) -> None:
    if head["title_count"] == 0:
        report.findings.append(
            Finding(
                severity="high",
                rule="missing_title",
                message="Page has no <title> element.",
            )
        )
        return

    if head["title_count"] > 1:
        report.findings.append(
            Finding(
                severity="high",
                rule="multiple_titles",
                message=f"Page has {head['title_count']} <title> elements. Only one is permitted.",
            )
        )

    title = (head["title"] or "").strip()
    if not title:
        report.findings.append(
            Finding(
                severity="high",
                rule="empty_title",
                message="<title> element is empty.",
            )
        )
        return

    if title.lower() in GENERIC_TITLE_VALUES:
        report.findings.append(
            Finding(
                severity="medium",
                rule="generic_title",
                message=f'<title> "{title}" looks like a CMS or template default, not descriptive content.',
                detail=title,
            )
        )


def check_canonical(
    page_url: str,
    head: dict[str, Any],
    report: PageReport,
    check_status: bool,
) -> None:
    if head["canonical_count"] == 0:
        report.findings.append(
            Finding(
                severity="high",
                rule="missing_canonical",
                message="Page has no <link rel=\"canonical\">.",
            )
        )
        return

    if head["canonical_count"] > 1:
        report.findings.append(
            Finding(
                severity="high",
                rule="multiple_canonicals",
                message=f"Page has {head['canonical_count']} canonical links. "
                "Google will typically ignore all of them and fall back to its own canonicalization.",
            )
        )

    canonical = head["canonical"]
    if not canonical:
        return

    if not (canonical.startswith("http://") or canonical.startswith("https://")):
        report.findings.append(
            Finding(
                severity="medium",
                rule="relative_canonical",
                message="Canonical URL is relative. Use absolute URLs with protocol and domain.",
                detail=canonical,
            )
        )
        return

    page_host = urlparse(page_url).netloc
    canonical_host = urlparse(canonical).netloc
    if page_host and canonical_host and page_host != canonical_host:
        report.findings.append(
            Finding(
                severity="medium",
                rule="canonical_host_mismatch",
                message=f"Canonical host '{canonical_host}' does not match page host '{page_host}'. "
                "This is valid for cross-domain canonicals but worth confirming.",
                detail=canonical,
            )
        )

    if check_status:
        try:
            status = fetch_status_only(canonical)
            if status != 200:
                report.findings.append(
                    Finding(
                        severity="high",
                        rule="canonical_not_200",
                        message=f"Canonical URL returns HTTP {status}, not 200. "
                        "Canonical signal is effectively lost.",
                        detail=canonical,
                    )
                )
        except Exception as exc:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="canonical_unreachable",
                    message=f"Canonical URL is unreachable: {exc}",
                    detail=canonical,
                )
            )


# Matches a `noindex` or `none` directive as a whole token. Google
# documents content="none" as equivalent to "noindex, nofollow", so it
# must be detected wherever a literal "noindex" would be.
_NOINDEX_DIRECTIVE = re.compile(r"(^|[\s,;:])(noindex|none)([\s,;]|$)", re.IGNORECASE)


def has_noindex(value: str | None) -> bool:
    if not value:
        return False
    return bool(_NOINDEX_DIRECTIVE.search(value))


def check_robots(
    head: dict[str, Any],
    response_headers: dict[str, str],
    should_index: bool,
    report: PageReport,
) -> None:
    """Check robots directives in meta tags and X-Robots-Tag header."""
    meta_noindex = has_noindex(head.get("robots")) or has_noindex(
        head.get("googlebot")
    )
    header_value = response_headers.get("x-robots-tag", "")
    header_noindex = has_noindex(header_value)

    has_any_noindex = meta_noindex or header_noindex

    if should_index and has_any_noindex:
        sources = []
        if meta_noindex:
            sources.append("<meta name=\"robots\">")
        if header_noindex:
            sources.append("X-Robots-Tag header")
        report.findings.append(
            Finding(
                severity="high",
                rule="noindex_on_indexable_page",
                message=f"Page is marked noindex via {' and '.join(sources)}, "
                "but the caller declared this URL as indexable. This is the Failure Mode 4 pattern.",
                detail=f"meta robots: {head.get('robots')!r}, "
                f"meta googlebot: {head.get('googlebot')!r}, "
                f"X-Robots-Tag: {header_value!r}",
            )
        )

    # Failure Mode 5: noindex page with canonical pointing elsewhere.
    if (
        has_any_noindex
        and head.get("canonical")
        and head.get("canonical_count") == 1
    ):
        # Self-canonical on a noindex page is fine. Canonical pointing to
        # a different URL on a noindex page is the conflict.
        try:
            from urllib.parse import urldefrag
            page_normalized, _ = urldefrag(
                report.url.rstrip("/")
            )
            canonical_normalized, _ = urldefrag(
                head["canonical"].rstrip("/")
            )
            if page_normalized != canonical_normalized:
                report.findings.append(
                    Finding(
                        severity="high",
                        rule="noindex_with_external_canonical",
                        message="Page is noindex and has a canonical pointing to a different URL. "
                        "Google will not consolidate signals to the canonical target. "
                        "Use a 301 redirect instead if signal consolidation is the intent.",
                        detail=f"canonical: {head['canonical']}",
                    )
                )
        except Exception:
            pass


def check_description(head: dict[str, Any], report: PageReport) -> None:
    if not head.get("description"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="missing_description",
                message="Page has no <meta name=\"description\">. Google may "
                "generate a snippet from page content, which may be less compelling than a written description.",
            )
        )
        return

    if head.get("description_count", 0) > 1:
        report.findings.append(
            Finding(
                severity="medium",
                rule="multiple_descriptions",
                message=f"Page has {head['description_count']} <meta name=\"description\"> tags. "
                "Google picks one unpredictably; emit exactly one.",
            )
        )


def check_charset(head: dict[str, Any], report: PageReport) -> None:
    charset = head.get("charset")
    if not charset:
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_charset",
                message="Page has no <meta charset>. Browsers fall back to "
                "heuristics or the HTTP header, which can mangle non-ASCII text.",
            )
        )
        return

    if charset.strip().lower() != "utf-8":
        report.findings.append(
            Finding(
                severity="low",
                rule="non_utf8_charset",
                message=f"Declared charset is '{charset}', not utf-8.",
                detail=charset,
            )
        )


def check_open_graph(head: dict[str, Any], report: PageReport) -> None:
    if not head.get("og_title"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_og_title",
                message="Page has no og:title. Social platforms will use the <title> as fallback.",
            )
        )

    if not head.get("og_image"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_og_image",
                message="Page has no og:image. Social cards will display without a visual.",
            )
        )

    if not head.get("og_url"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_og_url",
                message="Page has no og:url. Social platforms may use the request URL, including tracking parameters.",
            )
        )

    if not head.get("twitter_card"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_twitter_card",
                message="Page has no twitter:card. X (formerly Twitter) will fall back to OG tags if present.",
            )
        )


def check_viewport(head: dict[str, Any], report: PageReport) -> None:
    viewport = head.get("viewport")
    if not viewport:
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_viewport",
                message="Page has no viewport meta tag. Mobile rendering may be degraded.",
            )
        )
        return

    if "user-scalable=no" in viewport.replace(" ", "").lower():
        report.findings.append(
            Finding(
                severity="low",
                rule="viewport_blocks_zoom",
                message="Viewport has user-scalable=no. This harms accessibility.",
                detail=viewport,
            )
        )


def audit(
    url: str,
    should_index: bool = True,
    check_canonical_status: bool = False,
) -> PageReport:
    """Run the full audit for a URL."""
    report = PageReport(url=url)
    try:
        status, body, headers = fetch(url)
        report.status_code = status
        report.fetched = True
    except Exception as exc:
        report.error = str(exc)
        return report

    soup = BeautifulSoup(body, "html.parser")
    head = get_head_data(soup)

    check_title(head, report)
    check_canonical(url, head, report, check_canonical_status)
    check_robots(head, headers, should_index, report)
    check_description(head, report)
    check_open_graph(head, report)
    check_viewport(head, report)
    check_charset(head, report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single URL to audit.")
    source.add_argument(
        "--urls-file",
        help="Newline-separated list of URLs.",
    )
    source.add_argument(
        "--sitemap",
        help="Sitemap or sitemap-index URL to parse for URLs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap on the number of URLs to audit (useful with --sitemap).",
    )
    parser.add_argument(
        "--check-canonical-status",
        action="store_true",
        help="Also verify that each canonical URL returns HTTP 200. "
        "Slow on large URL sets.",
    )
    parser.add_argument(
        "--expect-noindex",
        action="store_true",
        help="For --url, mark the URL as intentionally non-indexable, so a "
        "noindex directive is expected rather than flagged. In a --urls-file, "
        "append a whitespace-separated 'noindex' token to a line for the same "
        "effect per URL.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write JSON output to. Defaults to stdout.",
    )
    args = parser.parse_args()

    # Each target is (url, should_index). should_index=False means the
    # URL is expected to be noindex, so a noindex directive is correct
    # rather than a finding.
    targets: list[tuple[str, bool]] = []
    if args.url:
        targets = [(args.url, not args.expect_noindex)]
    elif args.urls_file:
        for line in Path(args.urls_file).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Optional second whitespace-separated token: 'noindex' marks
            # the URL as intentionally non-indexable.
            parts = line.split(None, 1)
            url = parts[0]
            should_index = not (len(parts) == 2 and parts[1].strip().lower() == "noindex")
            targets.append((url, should_index))
        if args.limit:
            targets = targets[: args.limit]
    else:
        targets = [(url, True) for url in parse_sitemap(args.sitemap, limit=args.limit)]

    reports = []
    for url, should_index in targets:
        report = audit(
            url,
            should_index=should_index,
            check_canonical_status=args.check_canonical_status,
        )
        reports.append(report)
        counts = report.to_dict()["counts"]
        status = "OK" if counts["high"] == 0 else "FAIL"
        print(
            f"{status}\t{url}\th={counts['high']} m={counts['medium']} l={counts['low']}",
            file=sys.stderr,
        )

    out = {
        "reports": [r.to_dict() for r in reports],
        "summary": {
            "urls_audited": len(reports),
            "urls_fetched": sum(1 for r in reports if r.fetched),
            "high_severity_total": sum(
                r.to_dict()["counts"]["high"] for r in reports
            ),
            "medium_severity_total": sum(
                r.to_dict()["counts"]["medium"] for r in reports
            ),
            "low_severity_total": sum(
                r.to_dict()["counts"]["low"] for r in reports
            ),
        },
    }

    output_text = json.dumps(out, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)

    return 1 if out["summary"]["high_severity_total"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())