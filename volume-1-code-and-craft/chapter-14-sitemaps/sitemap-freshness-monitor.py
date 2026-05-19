#!/usr/bin/env python3
"""
sitemap-freshness-monitor.py

Validate that <lastmod> values in a sitemap correspond to actual content
changes, by hashing the visible page content of a sample of URLs and
comparing against a JSON state file across runs.

The two failure modes this catches that pure-static analysis cannot:

  - Overactive <lastmod>: a URL's <lastmod> advanced between runs but the
    hashed visible content did not change. Signature of a sitemap
    generator deriving <lastmod> from a deploy timestamp or row-level
    updated_at rather than a content-level timestamp.

  - Stale <lastmod>: the hashed visible content changed between runs but
    <lastmod> did not advance. Signature of a sitemap generator missing
    a content-change trigger, or of editorial edits that bypass the
    content_updated_at update path.

State is persisted as JSON between runs so the script can run on a
schedule (daily, weekly) and accumulate signal. A custom CSS selector
can be passed to scope the content hash to a specific region of the
page if the default heuristic is too broad or too narrow.

The default content-extraction heuristic prefers <main> or <article>
if present, otherwise falls back to <body>, and in both cases strips
<script>, <style>, <nav>, <header>, <footer>, <aside>, and <noscript>
before hashing.

Exits non-zero on any error-severity finding. Overactive and stale
<lastmod> findings are surfaced as warnings.
"""

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

import requests
from lxml import etree, html

MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
NS = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
USER_AGENT = 'SitemapFreshnessMonitor/1.0 (+chapter-14-tooling)'
DEFAULT_TIMEOUT = 15
DEFAULT_SAMPLE_SIZE = 50
DEFAULT_STATE_FILE = '.sitemap-freshness-state.json'
STRIP_TAGS = ('script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript')
LASTMOD_DATE_ONLY = re.compile(r'^\d{4}-\d{2}-\d{2}$')
LASTMOD_FULL = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$'
)


@dataclass
class Finding:
    severity: str
    check: str
    target_url: str | None
    detail: str


@dataclass
class Report:
    findings: list = field(default_factory=list)

    def add(self, severity, check, target_url, detail):
        self.findings.append(Finding(severity, check, target_url, detail))

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


def is_valid_lastmod(value):
    return bool(LASTMOD_FULL.match(value) or LASTMOD_DATE_ONLY.match(value))


def parse_lastmod_to_datetime(value):
    text = value if 'T' in value else value + 'T00:00:00+00:00'
    text = text.replace('Z', '+00:00')
    return datetime.fromisoformat(text)


def fetch_sitemap_bytes(url, report):
    try:
        resp = http_get(url)
    except requests.RequestException as e:
        report.add('error', 'sitemap_fetch', url, f'fetch failed: {e}')
        return None
    if resp.status_code != 200:
        report.add(
            'error', 'sitemap_fetch', url,
            f'sitemap returned HTTP {resp.status_code}',
        )
        return None

    raw = resp.content
    if raw[:2] == b'\x1f\x8b':
        try:
            raw = gzip.decompress(raw)
        except gzip.BadGzipFile as e:
            report.add('error', 'gzip', url, f'bad gzip payload: {e}')
            return None

    if len(raw) > MAX_UNCOMPRESSED_BYTES:
        report.add(
            'error', 'size', url,
            f'uncompressed size {len(raw)} exceeds 50 MB',
        )
    return raw


def parse_sitemap_xml(raw, sitemap_url, report):
    try:
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        return etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as e:
        report.add('error', 'xml_syntax', sitemap_url, f'malformed XML: {e}')
        return None


def collect_entries(root, sitemap_url, report, depth=0):
    if depth > 5:
        report.add(
            'error', 'sitemap_depth', sitemap_url,
            'sitemap index nesting exceeds 5 levels',
        )
        return []

    tag = etree.QName(root).localname
    if tag == 'sitemapindex':
        entries = []
        for s in root.findall('sm:sitemap/sm:loc', NS):
            if not (s.text and s.text.strip()):
                continue
            child_url = s.text.strip()
            raw = fetch_sitemap_bytes(child_url, report)
            if raw is None:
                continue
            child_root = parse_sitemap_xml(raw, child_url, report)
            if child_root is None:
                continue
            entries.extend(
                collect_entries(child_root, child_url, report, depth + 1)
            )
        return entries

    if tag == 'urlset':
        entries = []
        for url_el in root.findall('sm:url', NS):
            loc_el = url_el.find('sm:loc', NS)
            lastmod_el = url_el.find('sm:lastmod', NS)
            if loc_el is None or not loc_el.text:
                continue
            entries.append({
                'loc': loc_el.text.strip(),
                'lastmod': (
                    lastmod_el.text.strip()
                    if lastmod_el is not None and lastmod_el.text
                    else None
                ),
            })
        return entries

    return []


def extract_visible_text(body_bytes, selector):
    """
    Render the response body to a normalized text string for hashing.

    If a CSS selector is provided, only the matched subtree is hashed.
    Otherwise, prefer <main> or <article>, fall back to <body>. In every
    branch, STRIP_TAGS are removed before serialization so changes to
    navigation chrome or analytics inline scripts do not falsely signal a
    content change.
    """
    try:
        tree = html.fromstring(body_bytes)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return ''

    if selector:
        # Treat selectors that begin with /, ./, or ( as XPath; everything
        # else as a CSS selector. This is the same convention most lxml
        # tooling uses.
        is_xpath = selector.startswith(('/', './', '('))
        try:
            matches = tree.xpath(selector) if is_xpath else tree.cssselect(selector)
        except (etree.XPathEvalError, ValueError):
            matches = []
        if not matches:
            return ''
        roots = matches
    else:
        roots = (
            tree.cssselect('main')
            or tree.cssselect('article')
            or tree.cssselect('body')
            or [tree]
        )

    parts = []
    for root in roots:
        for el in root.iter():
            if el.tag in STRIP_TAGS:
                el.getparent().remove(el) if el.getparent() is not None else None
        text = root.text_content()
        parts.append(re.sub(r'\s+', ' ', text).strip())
    return '\n'.join(p for p in parts if p)


def hash_content(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def fetch_and_hash(url, selector, report):
    try:
        resp = http_get(url, allow_redirects=True)
    except requests.RequestException as e:
        report.add('error', 'url_fetch', url, f'fetch failed: {e}')
        return None
    if resp.status_code != 200:
        report.add(
            'warning', 'url_status', url,
            f'final status {resp.status_code}; skipping content hash',
        )
        return None
    text = extract_visible_text(resp.content, selector)
    if not text:
        report.add(
            'warning', 'empty_extract', url,
            'extracted visible text was empty; skipping content hash',
        )
        return None
    return hash_content(text)


def load_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path, state):
    with open(path, 'w') as f:
        json.dump(state, f, indent=2, sort_keys=True)


def compare_against_state(entry, prior, current_hash, report):
    """
    Emit overactive / stale findings by comparing this run's lastmod and
    content hash against the prior run's recorded values.
    """
    url = entry['loc']
    lastmod = entry['lastmod']
    prior_lastmod = prior.get('lastmod')
    prior_hash = prior.get('content_hash')

    if prior_hash is None or current_hash is None:
        return

    lastmod_advanced = False
    if lastmod and prior_lastmod and is_valid_lastmod(lastmod) and is_valid_lastmod(prior_lastmod):
        try:
            lastmod_advanced = (
                parse_lastmod_to_datetime(lastmod)
                > parse_lastmod_to_datetime(prior_lastmod)
            )
        except ValueError:
            lastmod_advanced = False
    elif lastmod and not prior_lastmod:
        lastmod_advanced = True

    content_changed = current_hash != prior_hash

    if lastmod_advanced and not content_changed:
        report.add(
            'warning', 'overactive_lastmod', url,
            f'<lastmod> advanced from {prior_lastmod} to {lastmod} '
            'but hashed visible content is unchanged',
        )
    elif content_changed and not lastmod_advanced:
        report.add(
            'warning', 'stale_lastmod', url,
            f'visible content changed but <lastmod> did not advance '
            f'(still {lastmod or "absent"})',
        )


def run(sitemap_url, args, report):
    raw = fetch_sitemap_bytes(sitemap_url, report)
    if raw is None:
        return None
    root = parse_sitemap_xml(raw, sitemap_url, report)
    if root is None:
        return None
    entries = collect_entries(root, sitemap_url, report)

    for entry in entries:
        if entry['lastmod'] and not is_valid_lastmod(entry['lastmod']):
            report.add(
                'error', 'lastmod_format', entry['loc'],
                f'invalid W3C datetime: {entry["lastmod"]}',
            )
        elif not entry['lastmod']:
            report.add(
                'info', 'lastmod_missing', entry['loc'],
                'no <lastmod> declared for this URL',
            )

    state = load_state(args.state_file)
    sample = entries[: args.sample]
    new_state = {}
    now = datetime.now(timezone.utc).isoformat()

    for entry in sample:
        url = entry['loc']
        current_hash = fetch_and_hash(url, args.selector, report)
        prior = state.get(url, {})
        compare_against_state(entry, prior, current_hash, report)
        new_state[url] = {
            'lastmod': entry['lastmod'],
            'content_hash': current_hash,
            'last_seen': now,
        }

    # Preserve state for URLs we did not sample this run, so a smaller
    # sample window does not erase accumulated history.
    for url, prior in state.items():
        if url not in new_state:
            new_state[url] = prior

    save_state(args.state_file, new_state)
    return new_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--sitemap', required=True,
        help='Sitemap or sitemap index URL',
    )
    parser.add_argument(
        '--sample', type=int, default=DEFAULT_SAMPLE_SIZE,
        help='URLs to fetch and hash this run',
    )
    parser.add_argument(
        '--selector',
        help=(
            'Optional CSS or XPath selector to scope the content hash. '
            'Selectors starting with /, ./, or ( are treated as XPath.'
        ),
    )
    parser.add_argument(
        '--state-file', default=DEFAULT_STATE_FILE,
        help='JSON file used to persist per-URL hashes across runs',
    )
    parser.add_argument('--output', help='Write JSON report to this file')
    args = parser.parse_args()

    report = Report()
    run(args.sitemap, args, report)

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report.to_dict(), f, indent=2)
    else:
        json.dump(report.to_dict(), sys.stdout, indent=2)
        print()

    sys.exit(1 if report.has_errors else 0)


if __name__ == '__main__':
    main()
