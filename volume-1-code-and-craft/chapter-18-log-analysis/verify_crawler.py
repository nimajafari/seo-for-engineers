#!/usr/bin/env python3
"""
verify_crawler.py

Multi-bot extension of Chapter 16's verify-googlebot.py. Loads
published IP ranges for the major search and AI crawlers (Google,
Bing, OpenAI, Anthropic, Apple) and verifies each log line's source
IP against the union of ranges, labeling the request with the
verified crawler name or marking it as spoofed when the User-Agent
claims a crawler whose IP ranges do not match.

The script doubles as a Python module: enrich_logs.py imports
load_all_crawlers and classify_ip from here to perform the same
verification in the DuckDB enrichment pipeline.

CLI usage:
    python verify_crawler.py --input access.log --format combined
    python verify_crawler.py --input access.log --output verified.ndjson
    python verify_crawler.py --input access.log --summary-only
    python verify_crawler.py --input access.log --crawlers googlebot,bingbot

For Googlebot-only workflows, prefer Chapter 16's verify-googlebot.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

CACHE_DIR = Path(os.path.expanduser('~/.cache/seo-crawler-ranges'))
CACHE_TTL_SECONDS = 24 * 60 * 60
USER_AGENT = 'VerifyCrawler/1.0 (+chapter-18-tooling)'
FETCH_TIMEOUT_SECONDS = 15


@dataclass
class Crawler:
    """
    A verifiable crawler.

    name:       canonical lowercase identifier used as the verified_crawler
                value in enriched logs.
    purpose:    one of 'search', 'ai_training', 'ai_search'. Drives the
                crawler_purpose column in enrich_logs.py.
    ua_tokens:  substrings to look for in the User-Agent header when
                evaluating spoofing in the CLI summary. Lookups are
                case-insensitive.
    ranges_url: URL of the published IP-range JSON. None marks the
                crawler as "unverifiable" (no public range list known
                to the script); classify_ip will never match it.
    networks:   parsed ipaddress.ip_network list, populated by
                load_all_crawlers.
    """
    name: str
    purpose: str
    ua_tokens: tuple
    ranges_url: str | None = None
    networks: list = field(default_factory=list)


# Crawler registry. URLs marked "best-effort" may 404 on some
# crawlers that do not publish a stable JSON endpoint; in that case
# the crawler is registered with an empty network list and a warning
# is printed at load time, so the rest of the pipeline still runs.
_CRAWLER_DEFS: tuple[Crawler, ...] = (
    Crawler(
        name='googlebot',
        purpose='search',
        ua_tokens=('Googlebot',),
        ranges_url='https://developers.google.com/search/apis/ipranges/googlebot.json',
    ),
    Crawler(
        name='special-crawlers',
        purpose='search',
        ua_tokens=('AdsBot', 'Storebot', 'Mediapartners', 'Googlebot-Image',
                   'Googlebot-News', 'Googlebot-Video'),
        ranges_url='https://developers.google.com/search/apis/ipranges/special-crawlers.json',
    ),
    Crawler(
        name='user-triggered-fetchers',
        purpose='search',
        ua_tokens=('Google-Site-Verification', 'FeedFetcher-Google',
                   'Google-Read-Aloud', 'APIs-Google'),
        ranges_url='https://developers.google.com/search/apis/ipranges/user-triggered-fetchers.json',
    ),
    Crawler(
        name='bingbot',
        purpose='search',
        ua_tokens=('bingbot', 'BingPreview'),
        ranges_url='https://www.bing.com/toolbox/bingbot.json',
    ),
    Crawler(
        name='gptbot',
        purpose='ai_training',
        ua_tokens=('GPTBot',),
        ranges_url='https://openai.com/gptbot.json',
    ),
    Crawler(
        name='oai_searchbot',
        purpose='ai_search',
        ua_tokens=('OAI-SearchBot',),
        ranges_url='https://openai.com/searchbot.json',
    ),
    Crawler(
        name='chatgpt_user',
        purpose='ai_search',
        ua_tokens=('ChatGPT-User',),
        ranges_url='https://openai.com/chatgpt-user.json',
    ),
    Crawler(
        name='claudebot',
        purpose='ai_training',
        ua_tokens=('ClaudeBot', 'Claude-User', 'anthropic-ai'),
        # Anthropic publishes the User-Agent strings in their docs but
        # does not (as of writing) publish a stable IP-range JSON. The
        # crawler is registered so the UA-claim side of the spoof check
        # still works; networks will be empty.
        ranges_url=None,
    ),
    Crawler(
        name='applebot',
        purpose='search',
        ua_tokens=('Applebot',),
        # Apple does not publish a JSON of Applebot ranges. Apple
        # documents the ranges only via the Search Help support page;
        # operators who need this should override at registration.
        ranges_url=None,
    ),
)


def _cache_path(crawler_name: str) -> Path:
    return CACHE_DIR / f'{crawler_name}.json'


def _fetch_with_cache(name: str, url: str) -> dict | None:
    cache_file = _cache_path(name)
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            try:
                return json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                pass  # fall through and refetch

    request = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            f'warning: failed to fetch {name} ranges from {url}: {exc}\n'
            f'         crawler will register with empty IP ranges\n'
        )
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps(data))
    return data


def _parse_ranges(data: dict) -> list:
    networks: list = []
    for prefix in data.get('prefixes', []):
        cidr = prefix.get('ipv4Prefix') or prefix.get('ipv6Prefix')
        if not cidr:
            continue
        try:
            networks.append(ipaddress.ip_network(cidr))
        except ValueError:
            continue
    return networks


def load_all_crawlers(filter_names: list | None = None) -> dict[str, Crawler]:
    """
    Load IP ranges for every registered crawler and return them as a
    dict keyed by crawler.name.

    filter_names: if provided, only the named crawlers are loaded.
    """
    selected = _CRAWLER_DEFS
    if filter_names:
        wanted = {name.strip().lower() for name in filter_names}
        selected = tuple(c for c in selected if c.name in wanted)

    loaded: dict[str, Crawler] = {}
    for definition in selected:
        crawler = Crawler(
            name=definition.name,
            purpose=definition.purpose,
            ua_tokens=definition.ua_tokens,
            ranges_url=definition.ranges_url,
        )
        if definition.ranges_url:
            data = _fetch_with_cache(definition.name, definition.ranges_url)
            if data is not None:
                crawler.networks = _parse_ranges(data)
        loaded[definition.name] = crawler

    return loaded


def classify_ip(ip_str: str, crawlers: dict[str, Crawler]) -> str | None:
    """
    Return the name of the crawler whose IP ranges include ip_str,
    or None if no crawler matches (or the IP is malformed).
    """
    if not ip_str:
        return None
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    for name, crawler in crawlers.items():
        if any(ip in net for net in crawler.networks):
            return name
    return None


def ua_claims_any_crawler(ua: str, crawlers: dict[str, Crawler]) -> str | None:
    """Return the name of the first crawler whose UA tokens appear in ua."""
    if not ua:
        return None
    ua_lower = ua.lower()
    for name, crawler in crawlers.items():
        if any(token.lower() in ua_lower for token in crawler.ua_tokens):
            return name
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_parse_logs():
    """Import parse_logs.py from the same directory for format support."""
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        'parse_logs', os.path.join(here, 'parse_logs.py')
    )
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules before exec_module so dataclass-style
    # introspection on Python 3.14+ can resolve the module reference.
    sys.modules['parse_logs'] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class VerificationStats:
    total: int = 0
    verified: Counter = field(default_factory=Counter)
    spoofed: Counter = field(default_factory=Counter)
    unparseable: int = 0


def run(args) -> int:
    parse_logs = _load_parse_logs()
    parser = parse_logs.PARSERS.get(args.format)
    if parser is None:
        sys.stderr.write(f'unknown format: {args.format}\n')
        return 2

    crawlers = load_all_crawlers(
        args.crawlers.split(',') if args.crawlers else None
    )
    stats = VerificationStats()

    if args.summary_only:
        out_handle = None
    elif args.output:
        out_handle = open(args.output, 'w', encoding='utf-8')
    else:
        out_handle = sys.stdout

    try:
        with parse_logs.open_input(args.input) as f:
            for line in f:
                if not line.strip():
                    continue
                record = parser(line)
                if record is None:
                    stats.unparseable += 1
                    continue

                stats.total += 1
                ip_match = classify_ip(record['remote_addr'], crawlers)
                ua_match = ua_claims_any_crawler(
                    record.get('user_agent', ''), crawlers
                )

                if ip_match:
                    stats.verified[ip_match] += 1
                    record['verified_crawler'] = ip_match
                    record['crawler_purpose'] = crawlers[ip_match].purpose
                    if out_handle is not None:
                        out_handle.write(json.dumps(record) + '\n')
                elif ua_match:
                    stats.spoofed[ua_match] += 1
    finally:
        if out_handle is not None and out_handle is not sys.stdout:
            out_handle.close()

    _write_summary(stats, sys.stderr)
    return 0


def _write_summary(stats: VerificationStats, stream) -> None:
    stream.write('\nverification summary\n')
    stream.write('-' * 60 + '\n')
    stream.write(f'total parsed:     {stats.total:>10}\n')
    stream.write(f'unparseable:      {stats.unparseable:>10}\n')

    verified_total = sum(stats.verified.values())
    stream.write(f'verified total:   {verified_total:>10}\n')
    if stats.verified:
        stream.write('\nverified by crawler:\n')
        for name, count in stats.verified.most_common():
            stream.write(f'  {name:25s} {count:>10}\n')

    if stats.spoofed:
        stream.write('\nspoofed (UA claims crawler, IP does not match):\n')
        for name, count in stats.spoofed.most_common():
            stream.write(f'  {name:25s} {count:>10}\n')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True,
                        help='Path to input log file, .gz supported, '
                             '- for stdin')
    parser.add_argument('--output',
                        help='Write verified records as JSON Lines '
                             '(default stdout)')
    parser.add_argument('--format', default='combined',
                        help='Input log format (see parse_logs.py)')
    parser.add_argument('--crawlers',
                        help='Comma-separated subset of crawler names to verify')
    parser.add_argument('--summary-only', action='store_true',
                        help='Suppress filtered log output')
    args = parser.parse_args()
    return run(args)


if __name__ == '__main__':
    sys.exit(main())
