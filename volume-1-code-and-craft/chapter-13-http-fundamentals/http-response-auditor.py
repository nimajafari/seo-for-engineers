#!/usr/bin/env python3
"""
http-response-auditor.py

Audit the HTTP responses of a population of URLs against the
correctness rules Chapter 13 of SEO for Engineers, Volume 1,
establishes as engineering standards.

Checks performed.

  1. Status code correctness, soft 404s, unexpected 404s.
  2. Redirect chain length.
  3. Redirect type correctness, 301 vs 302 for canonical patterns.
  4. Cache header anomalies, no-store on HTML, stale Last-Modified.
  5. Robots directive leakage, noindex in headers or markup.
  6. Mixed content on HTTPS pages.
  7. Conditional request support, 304 on unchanged content.
  8. Canonical signal conflicts, HTML vs HTTP header.
  9. Content-Type correctness.

Usage:
    python http-response-auditor.py --sitemap <url>
    python http-response-auditor.py --urls urls.txt
    python http-response-auditor.py --sitemap <url> --max-redirect-hops 2
    python http-response-auditor.py --sitemap <url> --output report.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 13.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from lxml import etree, html

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
REQUEST_TIMEOUT_SECONDS = 30
MAX_SITEMAP_INDEX_DEPTH = 3
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# Phrases that suggest the body is a soft-404 even when status is 200.
SOFT_404_PHRASES = [
    "page not found",
    "page cannot be found",
    "404 not found",
    "the requested url was not found",
    "this page doesn't exist",
    "this page does not exist",
    "sorry, we could not find",
    "the page you are looking for",
    "no results found",
    "out of stock",
    "no products match",
    "this product is no longer available",
]

# Upper bound on body length for the soft-404 heuristic. If a 200
# response is shorter than this and contains one of SOFT_404_PHRASES,
# the URL is flagged for review. Tuned to catch stub error pages
# while accepting small but legitimate content pages.
SOFT_404_BODY_LENGTH_CAP = 8000  # bytes
HTML_NOSTORE_DISABLES_BFCACHE = "no-store"


def _strip_www_prefix(host: str) -> str:
    """Strip a leading 'www.' label only; never an embedded one."""
    return host[4:] if host.startswith("www.") else host


def fetch_sitemap_content(source: str) -> bytes:
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
    if depth > MAX_SITEMAP_INDEX_DEPTH:
        return []
    try:
        content = fetch_sitemap_content(source)
        # Hardened parser: no external entity resolution and no network
        # entity loading, so a hostile sitemap cannot trigger XXE or
        # SSRF via DOCTYPE/ENTITY declarations. Matches chapter 14's
        # sitemap-auditor.
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        root = etree.fromstring(content, parser=parser)
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
    if args.sitemap:
        return parse_sitemap_urls(args.sitemap)
    if args.urls:
        return [
            line.strip()
            for line in Path(args.urls).read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    return []


def follow_redirects_manually(
    url: str, max_hops: int = 10
) -> tuple[list[dict[str, Any]], requests.Response | None]:
    """
    Walk redirects manually, recording each hop. Returns
    (chain, final_response). final_response is None if max_hops
    was exceeded, the fetch failed, or a redirect was missing
    its Location header.

    Uses GET (not HEAD) at every hop so the terminal response
    carries the body needed by downstream checks (canonical
    extraction, mixed-content scan, robots-meta lookup). Issuing
    HEAD then GET would double the request count per URL audited.
    """
    chain: list[dict[str, Any]] = []
    current_url = url

    for _ in range(max_hops):
        try:
            response = requests.get(
                current_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                allow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            )
        except Exception as exc:
            chain.append({"url": current_url, "error": str(exc)})
            return chain, None

        chain.append({
            "url": current_url,
            "status": response.status_code,
            "location": response.headers.get("Location"),
        })

        # Not a redirect: this is the terminal response, return it
        # directly so downstream checks can read its body.
        if response.status_code < 300 or response.status_code >= 400:
            return chain, response

        # Redirect status with no Location header is malformed.
        next_url = response.headers.get("Location")
        if not next_url:
            return chain, None
        current_url = urljoin(current_url, next_url)

    return chain, None


def check_redirect_chain(
    chain: list[dict[str, Any]], max_hops: int
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    redirect_hops = [h for h in chain if h.get("status", 200) >= 300]
    if len(redirect_hops) > max_hops:
        issues.append({
            "severity": "error",
            "rule": "redirect_chain_too_long",
            "message": (
                f"Redirect chain has {len(redirect_hops)} hops, "
                f"exceeds threshold of {max_hops}. Chain: "
                + " -> ".join(h["url"] for h in chain)
            ),
        })
    return issues


def check_redirect_types(
    chain: list[dict[str, Any]]
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for i, hop in enumerate(chain[:-1]):
        status = hop.get("status")
        next_url = hop.get("location")
        current_url = hop.get("url")
        if status != 302 or not next_url or not current_url:
            continue

        # Detect canonical-pattern redirects that should be 301.
        try:
            current_parsed = urlparse(current_url)
            next_parsed = urlparse(next_url)
        except Exception:
            continue

        # HTTP to HTTPS
        if current_parsed.scheme == "http" and next_parsed.scheme == "https":
            issues.append({
                "severity": "error",
                "rule": "wrong_redirect_type_http_to_https",
                "message": (
                    f"302 redirect from HTTP to HTTPS at hop {i}, "
                    "should be 301 for permanent protocol upgrade."
                ),
            })
        # www to non-www or non-www to www. Compare with prefix-only
        # stripping so an embedded "www." inside a host (e.g.,
        # "mail.www.example.com") is not silently elided.
        current_host = current_parsed.netloc.lower()
        next_host = next_parsed.netloc.lower()
        current_has_www = current_host.startswith("www.")
        next_has_www = next_host.startswith("www.")
        if current_has_www != next_has_www:
            if (
                _strip_www_prefix(current_host)
                == _strip_www_prefix(next_host)
            ):
                issues.append({
                    "severity": "error",
                    "rule": "wrong_redirect_type_www_normalization",
                    "message": (
                        f"302 redirect for www normalization at hop {i}, "
                        "should be 301."
                    ),
                })
        # Trailing slash normalization
        if (
            current_parsed.path.rstrip("/") == next_parsed.path.rstrip("/")
            and current_parsed.path != next_parsed.path
        ):
            issues.append({
                "severity": "error",
                "rule": "wrong_redirect_type_trailing_slash",
                "message": (
                    f"302 redirect for trailing slash normalization at hop {i}, "
                    "should be 301."
                ),
            })
    return issues


def check_status(
    url: str, response: requests.Response, declared_in_sitemap: bool
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if response.status_code == 404 and declared_in_sitemap:
        issues.append({
            "severity": "error",
            "rule": "sitemap_url_returns_404",
            "message": (
                f"URL {url} is declared in the sitemap but returns 404."
            ),
        })
    if 500 <= response.status_code < 600:
        # A 5xx on a public URL is a server-side failure that
        # blocks indexing entirely for as long as it persists.
        # Worth surfacing even if the URL is not in the sitemap.
        issues.append({
            "severity": "error",
            "rule": "server_error",
            "message": (
                f"URL {url} returns HTTP {response.status_code}. "
                "Crawlers treat sustained 5xx as a signal to slow "
                "or stop fetching the host."
            ),
        })
    return issues


def check_soft_404(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if response.status_code != 200:
        return issues
    body_lower = response.text.lower()
    body_length = len(response.text)
    matched = [p for p in SOFT_404_PHRASES if p in body_lower]
    if matched and body_length < SOFT_404_BODY_LENGTH_CAP:
        issues.append({
            "severity": "warning",
            "rule": "possible_soft_404",
            "message": (
                f"URL {url} returns 200 but body contains "
                f"not-found language: {matched[0]!r}. Possible soft 404. "
                "If this URL has no content, return 404 or 410."
            ),
        })
    return issues


def check_cache_headers(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return issues

    cache_control = response.headers.get("Cache-Control", "").lower()
    if HTML_NOSTORE_DISABLES_BFCACHE in cache_control:
        issues.append({
            "severity": "warning",
            "rule": "no_store_on_html_disables_bfcache",
            "message": (
                f"URL {url} sets Cache-Control: no-store on HTML, "
                "which disables bfcache and degrades INP on "
                "back-navigations."
            ),
        })

    # Check max-age on HTML (long values are usually a mistake).
    if cache_control:
        max_age_match = re.search(r"max-age=(\d+)", cache_control)
        if max_age_match:
            seconds = int(max_age_match.group(1))
            if seconds > 86400 * 7:  # 1 week
                issues.append({
                    "severity": "warning",
                    "rule": "long_max_age_on_html",
                    "message": (
                        f"URL {url} sets Cache-Control: max-age={seconds} "
                        "on HTML. Content changes will not reach crawlers "
                        "until the cache expires. Asset-style cache "
                        "headers on dynamic HTML is the typical cause."
                    ),
                })
    return issues


def check_robots_directives(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if response.status_code != 200:
        return issues

    # X-Robots-Tag header
    xrobots = response.headers.get("X-Robots-Tag", "").lower()
    if "noindex" in xrobots:
        issues.append({
            "severity": "error",
            "rule": "noindex_in_response_header",
            "message": (
                f"URL {url} has X-Robots-Tag: noindex. If this URL is "
                "intended to be indexed, this is the staging-to-production "
                "leakage failure mode."
            ),
        })

    # Meta robots in HTML
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" in content_type:
        try:
            doc = html.fromstring(response.content)
            metas = doc.xpath('//meta[@name="robots"]/@content')
            for m in metas:
                if "noindex" in m.lower():
                    issues.append({
                        "severity": "error",
                        "rule": "noindex_in_meta_tag",
                        "message": (
                            f"URL {url} has <meta name=\"robots\" "
                            f"content=\"{m}\">. If intended to be indexed, "
                            "this is a deployment regression."
                        ),
                    })
        except Exception:
            pass
    return issues


def check_mixed_content(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not url.startswith("https://"):
        return issues
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return issues

    try:
        doc = html.fromstring(response.content)
        # Sub-resource references via src or href that use plain http.
        http_refs = doc.xpath(
            '//*[(self::img or self::script or self::iframe '
            'or self::audio or self::video or self::source) '
            'and starts-with(@src, "http://")]/@src'
            ' | //link[starts-with(@href, "http://")]/@href'
        )
        if http_refs:
            issues.append({
                "severity": "error",
                "rule": "mixed_content_on_https",
                "message": (
                    f"URL {url} (HTTPS) loads {len(http_refs)} "
                    "subresource(s) over plain HTTP. Browsers block "
                    "or warn on these. Example: "
                    f"{http_refs[0]}"
                ),
            })
    except Exception:
        pass
    return issues


def check_canonical_conflict(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    content_type = response.headers.get("Content-Type", "").lower()
    if "text/html" not in content_type:
        return issues

    # Canonical from Link header.
    link_header = response.headers.get("Link", "")
    header_canonical = None
    for part in link_header.split(","):
        if 'rel="canonical"' in part or "rel=canonical" in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                header_canonical = urljoin(url, match.group(1))
                break

    # Canonical from HTML.
    html_canonical = None
    try:
        doc = html.fromstring(response.content)
        canonicals = doc.xpath('//link[@rel="canonical"]/@href')
        if canonicals:
            html_canonical = urljoin(url, canonicals[0])
    except Exception:
        pass

    if header_canonical and html_canonical:
        if header_canonical != html_canonical:
            issues.append({
                "severity": "error",
                "rule": "canonical_signal_conflict",
                "message": (
                    f"URL {url} has conflicting canonical signals. "
                    f"HTTP Link header: {header_canonical}. "
                    f"HTML <link rel=\"canonical\">: {html_canonical}. "
                    "Remove one to make the signal unambiguous."
                ),
            })
    return issues


def check_content_type(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    content_type = response.headers.get("Content-Type", "").lower()
    parsed = urlparse(url)
    path_lower = parsed.path.lower()

    if path_lower.endswith(".xml"):
        if "xml" not in content_type:
            issues.append({
                "severity": "warning",
                "rule": "sitemap_wrong_content_type",
                "message": (
                    f"URL {url} appears to be a sitemap but Content-Type "
                    f"is {content_type!r}. Should be application/xml."
                ),
            })
    elif path_lower.endswith("/robots.txt"):
        if "text/plain" not in content_type:
            issues.append({
                "severity": "warning",
                "rule": "robots_wrong_content_type",
                "message": (
                    f"URL {url} is robots.txt but Content-Type is "
                    f"{content_type!r}. Should be text/plain."
                ),
            })
    elif "text/html" in content_type and "charset" not in content_type:
        issues.append({
            "severity": "warning",
            "rule": "html_missing_charset",
            "message": (
                f"URL {url} returns text/html without a charset "
                "parameter. Should be text/html; charset=utf-8."
            ),
        })
    return issues


def check_conditional_requests(
    url: str, response: requests.Response
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if response.status_code != 200:
        return issues

    last_modified = response.headers.get("Last-Modified")
    etag = response.headers.get("ETag")

    if not last_modified and not etag:
        issues.append({
            "severity": "warning",
            "rule": "no_conditional_request_headers",
            "message": (
                f"URL {url} returns no Last-Modified or ETag. "
                "Crawlers cannot use conditional requests, wasting "
                "crawl budget on unchanged content."
            ),
        })
        return issues

    # Send a conditional request and check for 304. Target the final
    # (post-redirect) URL, not the original: the Last-Modified/ETag we
    # are validating belong to the terminal response, and re-requesting
    # a redirecting URL would just return the 3xx, producing a false
    # conditional_request_not_honored finding.
    final_url = response.url or url
    headers = {"User-Agent": USER_AGENT}
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    if etag:
        headers["If-None-Match"] = etag

    try:
        conditional_response = requests.get(
            final_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=headers,
            allow_redirects=False,
        )
    except Exception:
        return issues

    if conditional_response.status_code != 304:
        issues.append({
            "severity": "warning",
            "rule": "conditional_request_not_honored",
            "message": (
                f"URL {url} returns {conditional_response.status_code} "
                f"for a conditional request, expected 304. "
                "Last-Modified or ETag may advance on every request, "
                "negating crawl efficiency benefits."
            ),
        })
    return issues


def audit_url(
    url: str,
    declared_in_sitemap: bool,
    max_redirect_hops: int,
    skip_conditional: bool,
) -> list[dict[str, Any]]:
    chain, final_response = follow_redirects_manually(url)

    issues: list[dict[str, Any]] = []
    issues.extend(check_redirect_chain(chain, max_redirect_hops))
    issues.extend(check_redirect_types(chain))

    if final_response is None:
        issues.append({
            "severity": "error",
            "rule": "final_response_unreachable",
            "message": f"URL {url} could not be fully fetched.",
        })
        for issue in issues:
            issue["url"] = url
        return issues

    issues.extend(check_status(url, final_response, declared_in_sitemap))
    issues.extend(check_soft_404(url, final_response))
    issues.extend(check_cache_headers(url, final_response))
    issues.extend(check_robots_directives(url, final_response))
    issues.extend(check_mixed_content(url, final_response))
    issues.extend(check_canonical_conflict(url, final_response))
    issues.extend(check_content_type(url, final_response))
    if not skip_conditional:
        issues.extend(check_conditional_requests(url, final_response))

    for issue in issues:
        issue["url"] = url
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sitemap",
        help="Sitemap URL or local file path.",
    )
    parser.add_argument(
        "--urls",
        help="Path to a file with one URL per line.",
    )
    parser.add_argument(
        "--max-redirect-hops",
        type=int,
        default=1,
        help="Allowed number of redirect hops. Default 1 (single hop).",
    )
    parser.add_argument(
        "--skip-conditional",
        action="store_true",
        help="Skip conditional-request verification (faster).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the audit to the first N URLs.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the JSON report.",
    )
    args = parser.parse_args()

    if not args.sitemap and not args.urls:
        parser.error("Must provide --sitemap or --urls.")

    urls = load_urls(args)
    declared_in_sitemap = args.sitemap is not None
    if args.limit:
        urls = urls[: args.limit]
    print(f"Auditing {len(urls)} URLs.", file=sys.stderr)

    all_issues: list[dict[str, Any]] = []
    for i, url in enumerate(urls, 1):
        if i % 25 == 0:
            print(f"  ... {i}/{len(urls)}", file=sys.stderr)
        try:
            all_issues.extend(audit_url(
                url,
                declared_in_sitemap=declared_in_sitemap,
                max_redirect_hops=args.max_redirect_hops,
                skip_conditional=args.skip_conditional,
            ))
        except Exception as exc:
            all_issues.append({
                "severity": "error",
                "rule": "audit_exception",
                "url": url,
                "message": f"Audit raised exception, {exc}",
            })

    errors = [i for i in all_issues if i["severity"] == "error"]
    warnings = [i for i in all_issues if i["severity"] == "warning"]
    rule_counts: dict[str, int] = defaultdict(int)
    for issue in all_issues:
        rule_counts[issue["rule"]] += 1

    report = {
        "urls_audited": len(urls),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues_by_rule": dict(rule_counts),
        "issues": all_issues,
    }

    output_text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)

    print(
        f"\nResult, {len(errors)} errors, {len(warnings)} warnings "
        f"across {len(urls)} URLs.",
        file=sys.stderr,
    )
    print("By rule:", file=sys.stderr)
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1]):
        print(f"  {rule}, {count}", file=sys.stderr)

    if not args.output:
        print(output_text)

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())