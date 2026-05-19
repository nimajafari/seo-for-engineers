#!/usr/bin/env python3
"""
sitemap-auditor.py

Audit a sitemap (or sitemap index) against the failure modes
catalogued in Chapter 14 of SEO for Engineers, Volume 1.

Sitemap-level checks:
  1. Content-Type header correctness.
  2. Gzip decompression and size limit (50 MB uncompressed).
  3. Well-formed XML (hardened parser, no external entities).
  4. URL count limit (50,000 per sitemap).
  5. <lastmod> format validity (W3C datetime subset of ISO 8601).
  6. <lastmod> distribution sanity (deploy-timestamp bug detector).

Per-URL checks (sampled):
  7. Robots.txt allowance.
  8. HTTP status code, with redirect chain walking.
  9. Redirect chain length.
 10. X-Robots-Tag and <meta name="robots"> noindex.
 11. Canonical tag match.
 12. Staging-domain leak.

Exits non-zero on any error-severity finding.
"""

import argparse
import gzip
import json
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime
from urllib.robotparser import RobotFileParser

import requests
from lxml import etree

MAX_URLS_PER_SITEMAP = 50_000
MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
USER_AGENT = 'SitemapAuditor/1.0 (+chapter-14-tooling)'
DEFAULT_TIMEOUT = 15
DEFAULT_SAMPLE_SIZE = 50
STAGING_PATTERNS = (
    re.compile(r'\bstaging\b'),
    re.compile(r'\bstage\b'),
    re.compile(r'\bdev\b'),
    re.compile(r'\btest\b'),
    re.compile(r'\bpreview\b'),
    re.compile(r'\.local\b'),
)
LASTMOD_DATE_ONLY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
LASTMOD_FULL = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


@dataclass
class Finding:
    severity: str
    check: str
    sitemap_url: str
    target_url: str | None
    detail: str


@dataclass
class Report:
    findings: list = field(default_factory=list)

    def add(self, severity, check, sitemap_url, target_url, detail):
        self.findings.append(
            Finding(severity, check, sitemap_url, target_url, detail)
        )

    @property
    def has_errors(self):
        return any(f.severity == 'error' for f in self.findings)

    def to_dict(self):
        return {'findings': [asdict(f) for f in self.findings]}


def http_get(url, **kwargs):
    return requests.get(
        url,
        headers={'User-Agent': USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        **kwargs,
    )


def load_robots(base_url):
    rp = RobotFileParser()
    robots_url = urllib.parse.urljoin(base_url, '/robots.txt')
    try:
        rp.set_url(robots_url)
        rp.read()
    except Exception:
        return None
    return rp


def looks_like_staging(url):
    host = (urllib.parse.urlparse(url).hostname or '').lower()
    return any(pat.search(host) for pat in STAGING_PATTERNS)


def is_valid_lastmod(value):
    return bool(LASTMOD_FULL.match(value) or LASTMOD_DATE_ONLY.match(value))


def parse_lastmod_to_datetime(value):
    text = value if 'T' in value else value + 'T00:00:00+00:00'
    text = text.replace('Z', '+00:00')
    return datetime.fromisoformat(text)


def normalize_url(url, form):
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path
    if form == 'trailing_slash' and not path.endswith('/'):
        path = path + '/'
    elif form == 'no_trailing_slash' and path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    return urllib.parse.urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.query,
        '',
    ))


def fetch_sitemap_bytes(url, report):
    try:
        resp = http_get(url)
    except requests.RequestException as e:
        report.add('error', 'sitemap_fetch', url, None, f'fetch failed: {e}')
        return None
    if resp.status_code != 200:
        report.add(
            'error', 'sitemap_fetch', url, None,
            f'sitemap returned HTTP {resp.status_code}',
        )
        return None

    content_type = (resp.headers.get('Content-Type') or '').lower()
    accepted_types = ('xml', 'gzip')
    if not any(token in content_type for token in accepted_types):
        report.add(
            'warning', 'content_type', url, None,
            f'expected application/xml or application/gzip, '
            f'got {content_type or "no Content-Type"}',
        )

    raw = resp.content
    if raw[:2] == b'\x1f\x8b':
        try:
            raw = gzip.decompress(raw)
        except gzip.BadGzipFile as e:
            report.add('error', 'gzip', url, None, f'bad gzip payload: {e}')
            return None

    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        report.add(
            'error', 'size', url, None,
            f'uncompressed size {len(raw)} exceeds 50 MB',
        )
    return raw


def parse_sitemap_xml(raw, sitemap_url, report):
    try:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
        )
        return etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as e:
        report.add('error', 'xml_syntax', sitemap_url, None, f'malformed XML: {e}')
        return None


def collect_entries(root):
    tag = etree.QName(root).localname
    if tag == 'sitemapindex':
        children = [
            s.text.strip()
            for s in root.findall('sm:sitemap/sm:loc', NS)
            if s.text
        ]
        return children, True
    if tag == 'urlset':
        entries = []
        for url_el in root.findall('sm:url', NS):
            loc_el = url_el.find('sm:loc', NS)
            lastmod_el = url_el.find('sm:lastmod', NS)
            if loc_el is not None and loc_el.text:
                entries.append({
                    'loc': loc_el.text.strip(),
                    'lastmod': (
                        lastmod_el.text.strip()
                        if lastmod_el is not None and lastmod_el.text
                        else None
                    ),
                })
        return entries, False
    return [], False


def check_lastmod_distribution(entries, sitemap_url, report):
    timestamps = []
    for entry in entries:
        if not entry['lastmod']:
            continue
        if not is_valid_lastmod(entry['lastmod']):
            report.add(
                'error', 'lastmod_format', sitemap_url, entry['loc'],
                f'invalid W3C datetime: {entry["lastmod"]}',
            )
            continue
        try:
            timestamps.append(parse_lastmod_to_datetime(entry['lastmod']))
        except ValueError:
            continue
    if len(timestamps) < 10:
        return
    spread = (max(timestamps) - min(timestamps)).total_seconds()
    if spread < 3600:
        report.add(
            'warning', 'lastmod_distribution', sitemap_url, None,
            f'{len(timestamps)} URLs share a <lastmod> window under 1 hour; '
            'likely a deploy-timestamp bug',
        )


def check_url(entry, sitemap_url, robots, max_hops, canonical_form, report):
    target = entry['loc']

    if looks_like_staging(target):
        report.add(
            'error', 'staging_leak', sitemap_url, target,
            'sitemap URL host matches a staging pattern',
        )

    if robots is not None and not robots.can_fetch(USER_AGENT, target):
        report.add(
            'error', 'robots_disallow', sitemap_url, target,
            'URL is disallowed by robots.txt',
        )

    try:
        resp = http_get(target, allow_redirects=False)
    except requests.RequestException as e:
        report.add('error', 'url_fetch', sitemap_url, target, f'fetch failed: {e}')
        return

    hops = 0
    final = resp
    # Walk a few hops past max_hops so we can still identify the terminus
    # and report its status. The chain-length warning is emitted separately
    # below once max_hops is exceeded.
    while final.is_redirect and hops <= max_hops + 4:
        location = final.headers.get('Location')
        if not location:
            break
        hops += 1
        next_url = urllib.parse.urljoin(target, location)
        try:
            final = http_get(next_url, allow_redirects=False)
        except requests.RequestException as e:
            report.add(
                'error', 'url_fetch', sitemap_url, target,
                f'redirect fetch failed at hop {hops}: {e}',
            )
            return

    if hops > max_hops:
        report.add(
            'warning', 'redirect_chain', sitemap_url, target,
            f'{hops} redirect hops; expected at most {max_hops}',
        )

    if final.status_code >= 400:
        report.add(
            'error', 'http_status', sitemap_url, target,
            f'final status {final.status_code}',
        )
        return
    if 300 <= final.status_code < 400:
        report.add(
            'error', 'http_status', sitemap_url, target,
            f'unresolved redirect, final status {final.status_code}',
        )
        return

    headers_xrobots = (final.headers.get('X-Robots-Tag') or '').lower()
    if 'noindex' in headers_xrobots:
        report.add(
            'error', 'noindex', sitemap_url, target,
            'X-Robots-Tag: noindex on a sitemap URL',
        )

    body = final.text
    if re.search(
        r'<meta[^>]+name=["\']robots["\'][^>]+content=["\'][^"\']*noindex',
        body, re.IGNORECASE,
    ):
        report.add(
            'error', 'noindex', sitemap_url, target,
            '<meta name="robots" content="noindex"> on a sitemap URL',
        )

    canonical_match = re.search(
        r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']+)["\']',
        body, re.IGNORECASE,
    )
    if canonical_match and canonical_form != 'any':
        canonical = urllib.parse.urljoin(target, canonical_match.group(1))
        if normalize_url(target, canonical_form) != normalize_url(canonical, canonical_form):
            report.add(
                'warning', 'canonical_mismatch', sitemap_url, target,
                f'sitemap URL does not match canonical: {canonical}',
            )


def audit(sitemap_url, args, report, seen):
    if sitemap_url in seen:
        return
    seen.add(sitemap_url)

    raw = fetch_sitemap_bytes(sitemap_url, report)
    if raw is None:
        return

    root = parse_sitemap_xml(raw, sitemap_url, report)
    if root is None:
        return

    entries, is_index = collect_entries(root)
    if is_index:
        for child in entries:
            audit(child, args, report, seen)
        return

    if len(entries) > MAX_URLS_PER_SITEMAP:
        report.add(
            'error', 'url_count', sitemap_url, None,
            f'{len(entries)} URLs exceeds limit of {MAX_URLS_PER_SITEMAP}',
        )

    check_lastmod_distribution(entries, sitemap_url, report)

    sample = entries[: args.sample]
    robots = load_robots(sitemap_url)
    for entry in sample:
        check_url(
            entry,
            sitemap_url,
            robots,
            max_hops=args.max_redirect_hops,
            canonical_form=args.canonical_form,
            report=report,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--sitemap', required=True,
        help='Sitemap or sitemap index URL',
    )
    parser.add_argument(
        '--sample', type=int, default=DEFAULT_SAMPLE_SIZE,
        help='URLs per sitemap to sample for per-URL checks',
    )
    parser.add_argument(
        '--max-redirect-hops', type=int, default=1,
        help='Max acceptable redirect hops before a URL is flagged',
    )
    parser.add_argument(
        '--canonical-form',
        choices=['trailing_slash', 'no_trailing_slash', 'any'],
        default='any',
        help='Expected canonical URL form for normalization',
    )
    parser.add_argument('--output', help='Write JSON report to this file')
    args = parser.parse_args()

    report = Report()
    audit(args.sitemap, args, report, seen=set())

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
    else:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        print()

    sys.exit(1 if report.has_errors else 0)


if __name__ == '__main__':
    main()