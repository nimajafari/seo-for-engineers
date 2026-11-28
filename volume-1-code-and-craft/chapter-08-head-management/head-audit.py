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
canonical URLs, canonical host mismatches, generic title values (or
the og:site_name alone), and a missing or duplicated meta description.
Low severity findings include missing OG and X card markup, missing or
misconfigured viewport, and a missing or non-UTF-8 charset.

URLs can be sourced from --url, --urls-file, or --sitemap.

Usage:
    python head-audit.py --url https://example.com/
    python head-audit.py --urls-file urls.txt
    python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50
    python head-audit.py --url https://example.com/ --check-canonical-status
    python head-audit.py --url https://example.com/account --expect-noindex

Title, canonical, and the other head metadata are read from <head>
only, so an SVG <title> or a <link rel="canonical"> in the body is not
mistaken for the page's own (Google ignores body canonicals). Robots
meta tags are read from the whole document and every one counts, with
names matched case-insensitively, because a missed noindex is the
expensive failure. Redirects are followed and the final URL is the one
audited.

Exit codes: 0 no high-severity findings, 1 at least one high-severity
finding, 2 usage error or a URL that could not be audited (network
error or HTTP status >= 400) and no high-severity findings elsewhere.

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
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit

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

# Robots directives that carry a value after a colon. Any other
# "word:" prefix in a robots value names a user agent, as in
# "X-Robots-Tag: googlebot: noindex".
VALUE_DIRECTIVES = {
    "max-snippet",
    "max-image-preview",
    "max-video-preview",
    "unavailable_after",
}
# Google documents "none" as equivalent to "noindex, nofollow".
NOINDEX_DIRECTIVES = {"noindex", "none"}


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
    final_url: str | None = None
    fetched: bool = False
    status_code: int | None = None
    error: str | None = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
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


@dataclass
class Fetched:
    """The parts of an HTTP response the audit uses."""

    status: int
    url: str  # final URL, after redirects
    body: bytes
    charset: str | None
    x_robots_tag: list[str]


def header_charset(content_type: str | None) -> str | None:
    """The charset parameter of a Content-Type value, if any."""
    if not content_type:
        return None
    match = re.search(r'charset\s*=\s*"?([^";\s]+)', content_type, re.IGNORECASE)
    return match.group(1) if match else None


def fetch(url: str) -> Fetched:
    """GET a URL, following redirects. Raises requests.RequestException
    on network errors; HTTP error statuses are returned, not raised."""
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    # Keep each X-Robots-Tag header separate: requests joins repeated
    # headers with ", ", which blurs a "googlebot:" prefix in one header
    # into the directives of the next.
    raw_headers = getattr(response.raw, "headers", None)
    if raw_headers is not None and hasattr(raw_headers, "getlist"):
        x_robots_tag = raw_headers.getlist("X-Robots-Tag")
    else:
        value = response.headers.get("X-Robots-Tag")
        x_robots_tag = [value] if value else []
    return Fetched(
        status=response.status_code,
        url=response.url,
        body=response.content,
        charset=header_charset(response.headers.get("Content-Type")),
        x_robots_tag=x_robots_tag,
    )


def parse(body: bytes | str, charset: str | None = None) -> BeautifulSoup:
    """Parse HTML. Bytes are decoded with the header charset when there
    is one, otherwise BeautifulSoup sniffs the <meta charset> and the
    byte content, which avoids requests' ISO-8859-1 default for text/html
    responses without a charset."""
    if isinstance(body, bytes):
        return BeautifulSoup(body, "html.parser", from_encoding=charset)
    return BeautifulSoup(body, "html.parser")


def canonical_status(url: str) -> tuple[int, str | None]:
    """Status of the canonical URL itself, without following redirects,
    and the redirect target if there is one. A canonical that redirects
    is canonical drift, so the redirect must not be followed to a 200.
    Falls back to GET for servers that reject HEAD."""
    response = requests.head(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=False,
    )
    if response.status_code in (405, 501):
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
            allow_redirects=False,
            stream=True,
        )
        response.close()
    return response.status_code, response.headers.get("Location")


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
                remaining = None if limit is None else limit - len(urls)
                urls.extend(parse_sitemap(loc.text.strip(), limit=remaining))
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


def _in_foreign_content(tag) -> bool:
    """True inside <svg> or <math>, whose <title> is not the page title."""
    return tag.find_parent(["svg", "math"]) is not None


def get_head_data(soup: BeautifulSoup) -> dict[str, Any]:
    """Extract head element data into a structured dict."""
    # Head metadata only counts inside <head>. Without an explicit
    # <head> (html.parser does not infer one), use the whole document,
    # still skipping SVG and MathML.
    scope = soup.head or soup

    def in_scope(tags):
        return [t for t in tags if not _in_foreign_content(t)]

    metas = in_scope(scope.find_all("meta"))

    def attr_is(tag, attr: str, value: str) -> bool:
        return (tag.get(attr) or "").strip().lower() == value

    def meta_content(key: str, attrs: tuple[str, ...] = ("name",)) -> str | None:
        for tag in metas:
            if any(attr_is(tag, attr, key) for attr in attrs):
                return tag.get("content")
        return None

    def robots_contents(key: str) -> str | None:
        # Every robots tag counts (Google combines them), wherever it
        # appears, and the name is case-insensitive.
        values = [
            tag.get("content") or ""
            for tag in soup.find_all("meta")
            if attr_is(tag, "name", key)
        ]
        return ", ".join(values) if values else None

    titles = in_scope(scope.find_all("title"))
    canonical_tags = [
        tag
        for tag in in_scope(scope.find_all("link"))
        if "canonical" in [rel.lower() for rel in (tag.get("rel") or [])]
    ]
    description_tags = [t for t in metas if attr_is(t, "name", "description")]

    charset = None
    for tag in metas:
        if tag.get("charset"):
            charset = tag["charset"].strip()
            break
        if attr_is(tag, "http-equiv", "content-type"):
            charset = header_charset(tag.get("content"))
            if charset:
                break

    canonical = None
    if canonical_tags:
        canonical = (canonical_tags[0].get("href") or "").strip() or None

    return {
        "title_count": len(titles),
        "title": " ".join(titles[0].get_text().split()) if titles else None,
        "description": meta_content("description"),
        "description_count": len(description_tags),
        "charset": charset,
        "robots": robots_contents("robots"),
        "googlebot": robots_contents("googlebot"),
        "viewport": meta_content("viewport"),
        "canonical_count": len(canonical_tags),
        "canonical": canonical,
        "og_title": meta_content("og:title", ("property",)),
        "og_description": meta_content("og:description", ("property",)),
        "og_image": meta_content("og:image", ("property",)),
        "og_url": meta_content("og:url", ("property",)),
        "og_site_name": meta_content("og:site_name", ("property",)),
        # X reads twitter:* from name=, but property= is common and works.
        "twitter_card": meta_content("twitter:card", ("name", "property")),
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

    site_name = (head.get("og_site_name") or "").strip().lower()
    if title.lower() in GENERIC_TITLE_VALUES or (site_name and title.lower() == site_name):
        report.findings.append(
            Finding(
                severity="medium",
                rule="generic_title",
                message=f'<title> "{title}" looks like a CMS or template default '
                "(or the site name alone), not descriptive content.",
                detail=title,
            )
        )


def _host(url: str) -> str:
    """Lowercased host, plus the port when it is not the scheme default."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    default = {"http": 80, "https": 443}.get(parts.scheme.lower())
    host = parts.hostname or ""
    return host if port in (None, default) else f"{host}:{port}"


def normalize_url(url: str) -> str:
    """Compare-friendly URL: scheme and host lowercased, default port,
    fragment and trailing slash dropped."""
    parts = urlsplit(urldefrag(url)[0])
    return urlunsplit(
        (parts.scheme.lower(), _host(url), parts.path.rstrip("/"), parts.query, "")
    )


def is_absolute_http(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme.lower() in ("http", "https") and bool(parts.netloc)


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
        report.findings.append(
            Finding(
                severity="high",
                rule="missing_canonical",
                message="<link rel=\"canonical\"> has no href, so it names no canonical URL.",
            )
        )
        return

    if not is_absolute_http(canonical):
        report.findings.append(
            Finding(
                severity="medium",
                rule="relative_canonical",
                message="Canonical URL is relative. Use absolute URLs with protocol and domain.",
                detail=canonical,
            )
        )
        return

    page_host = _host(page_url)
    canonical_host = _host(canonical)
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
            status, location = canonical_status(canonical)
        except requests.RequestException as exc:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="canonical_unreachable",
                    message=f"Canonical URL is unreachable: {exc}",
                    detail=canonical,
                )
            )
            return
        if 300 <= status < 400:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="canonical_not_200",
                    message=f"Canonical URL redirects (HTTP {status} to {location}). "
                    "Point the canonical at the final URL.",
                    detail=canonical,
                )
            )
        elif status != 200:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="canonical_not_200",
                    message=f"Canonical URL returns HTTP {status}, not 200. "
                    "Canonical signal is effectively lost.",
                    detail=canonical,
                )
            )


def robots_directives(value: str | None) -> list[tuple[str | None, str]]:
    """Split a robots meta content or X-Robots-Tag value into
    (user_agent, directive) pairs, directive names lowercased.

    "googlebot: noindex" scopes the directives after it to googlebot,
    while "max-image-preview:none" is one directive whose value happens
    to be "none", not the "none" directive.
    """
    pairs: list[tuple[str | None, str]] = []
    agent: str | None = None
    for token in re.split(r"[,;]", value or ""):
        token = token.strip()
        name, sep, rest = token.partition(":")
        if sep and name.strip().lower() not in VALUE_DIRECTIVES:
            agent = name.strip().lower()
            token = rest.strip()
            name, sep, rest = token.partition(":")
        if sep:
            pairs.append((agent, name.strip().lower()))
        else:
            pairs.extend((agent, word) for word in token.lower().split())
    return pairs


def has_noindex(value: str | None) -> bool:
    """True when the value carries noindex or none, for any user agent."""
    return any(d in NOINDEX_DIRECTIVES for _, d in robots_directives(value))


def check_robots(
    head: dict[str, Any],
    x_robots_tag: list[str],
    should_index: bool,
    report: PageReport,
    page_url: str | None = None,
) -> None:
    """Check robots directives in meta tags and X-Robots-Tag headers."""
    page_url = page_url or report.url
    meta_noindex = has_noindex(head.get("robots")) or has_noindex(
        head.get("googlebot")
    )
    header_noindex = any(has_noindex(v) for v in x_robots_tag)
    header_value = ", ".join(x_robots_tag)

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
    # Self-canonical on a noindex page is fine. The canonical is resolved
    # against the final page URL, so a relative self-canonical or one
    # reached through a redirect is still recognised as self.
    if has_any_noindex and head.get("canonical") and head.get("canonical_count") == 1:
        target = urljoin(page_url, head["canonical"])
        if normalize_url(target) != normalize_url(page_url):
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
                message="Page declares no charset in <meta charset> or <meta http-equiv>. Browsers fall back to "
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
        fetched = fetch(url)
    except requests.RequestException as exc:
        report.error = str(exc)
        return report

    report.status_code = fetched.status
    report.final_url = fetched.url
    if fetched.status >= 400:
        # An error page's <head> says nothing about the real page.
        report.error = f"HTTP {fetched.status}"
        return report
    report.fetched = True

    head = get_head_data(parse(fetched.body, fetched.charset))

    check_title(head, report)
    check_canonical(fetched.url, head, report, check_canonical_status)
    check_robots(head, fetched.x_robots_tag, should_index, report, page_url=fetched.url)
    check_description(head, report)
    check_open_graph(head, report)
    check_viewport(head, report)
    check_charset(head, report)

    return report


def read_targets(path: str) -> list[tuple[str, bool]]:
    """Read (url, should_index) pairs from a urls file. Raises OSError
    or UnicodeDecodeError when the file cannot be read."""
    targets: list[tuple[str, bool]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Optional second whitespace-separated token: 'noindex' marks
        # the URL as intentionally non-indexable.
        parts = line.split(None, 1)
        should_index = not (len(parts) == 2 and parts[1].strip().lower() == "noindex")
        targets.append((parts[0], should_index))
    return targets


def positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def status_label(report: PageReport) -> str:
    if not report.fetched:
        return "ERROR"
    return "FAIL" if report.to_dict()["counts"]["high"] else "OK"


def exit_code(reports: list[PageReport]) -> int:
    """1 if any page has a high finding, else 2 if any page could not
    be audited, else 0."""
    labels = [status_label(r) for r in reports]
    if "FAIL" in labels:
        return 1
    if "ERROR" in labels:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
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
        type=positive_int,
        default=None,
        help="Audit only the first N URLs (useful with --sitemap).",
    )
    parser.add_argument(
        "--check-canonical-status",
        action="store_true",
        help="Also verify that each canonical URL returns HTTP 200 itself, "
        "without redirecting. Slow on large URL sets.",
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
        try:
            targets = read_targets(args.urls_file)
        except (OSError, UnicodeDecodeError) as exc:
            parser.error(f"cannot read --urls-file {args.urls_file}: {exc}")
        if not targets:
            parser.error(f"--urls-file {args.urls_file} lists no URLs")
        if args.limit:
            targets = targets[: args.limit]
    else:
        try:
            urls = parse_sitemap(args.sitemap, limit=args.limit)
        except (requests.RequestException, etree.XMLSyntaxError) as exc:
            print(f"head-audit: cannot read sitemap {args.sitemap}: {exc}", file=sys.stderr)
            return 2
        if not urls:
            print(f"head-audit: sitemap {args.sitemap} lists no URLs", file=sys.stderr)
            return 2
        targets = [(url, True) for url in urls]

    reports = []
    for url, should_index in targets:
        report = audit(
            url,
            should_index=should_index,
            check_canonical_status=args.check_canonical_status,
        )
        reports.append(report)
        counts = report.to_dict()["counts"]
        summary = report.error or f"h={counts['high']} m={counts['medium']} l={counts['low']}"
        print(f"{status_label(report)}\t{url}\t{summary}", file=sys.stderr)

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

    return exit_code(reports)


if __name__ == "__main__":
    sys.exit(main())
