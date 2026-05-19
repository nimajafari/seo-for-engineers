#!/usr/bin/env python3
"""
verify-googlebot.py

Filter a server access log to verified Googlebot requests. A request
is accepted only if both the source IP falls within Google's
published Googlebot IP ranges and the User-Agent contains a known
Googlebot product token.

The IP ranges are fetched from Google's public JSON endpoint and
cached locally for 24 hours. Forward and reverse DNS verification
(the alternative method documented by Google) is slower and not
implemented here; the IP-range method is preferred for bulk log
processing.

Output is the subset of input lines that pass verification. A
summary of accepted vs rejected requests is written to stderr.
"""

import argparse
import gzip
import ipaddress
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass

GOOGLEBOT_RANGES_URL = (
    'https://developers.google.com/search/apis/ipranges/googlebot.json'
)
DEFAULT_CACHE_PATH = os.path.expanduser('~/.cache/googlebot-ranges.json')
CACHE_TTL_SECONDS = 24 * 60 * 60

GOOGLEBOT_TOKENS = (
    'Googlebot',
    'Googlebot-Image',
    'Googlebot-News',
    'Googlebot-Video',
    'Storebot-Google',
    'AdsBot-Google',
    'AdsBot-Google-Mobile',
    'Mediapartners-Google',
    'APIs-Google',
    'FeedFetcher-Google',
    'Google-Read-Aloud',
    'GoogleOther',
)
STRICT_GOOGLEBOT_TOKENS = ('Googlebot',)


@dataclass
class Stats:
    accepted: int = 0
    rejected_ip: int = 0
    rejected_ua: int = 0
    rejected_both: int = 0
    unparseable: int = 0

    @property
    def total(self):
        return (
            self.accepted
            + self.rejected_ip
            + self.rejected_ua
            + self.rejected_both
            + self.unparseable
        )


def load_googlebot_ranges(cache_path, refresh=False):
    if not refresh and os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < CACHE_TTL_SECONDS:
            with open(cache_path) as f:
                return _parse_ranges(json.load(f))

    sys.stderr.write(
        f'fetching Googlebot IP ranges from {GOOGLEBOT_RANGES_URL}\n'
    )
    req = urllib.request.Request(
        GOOGLEBOT_RANGES_URL,
        headers={'User-Agent': 'VerifyGooglebot/1.0 (+chapter-16-tooling)'},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.load(response)

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, 'w') as f:
        json.dump(data, f)

    return _parse_ranges(data)


def _parse_ranges(data):
    networks = []
    for prefix in data.get('prefixes', []):
        if 'ipv4Prefix' in prefix:
            networks.append(ipaddress.ip_network(prefix['ipv4Prefix']))
        elif 'ipv6Prefix' in prefix:
            networks.append(ipaddress.ip_network(prefix['ipv6Prefix']))
    return networks


def ip_in_networks(ip_str, networks):
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def ua_matches_googlebot(ua, tokens):
    if not ua:
        return False
    ua_lower = ua.lower()
    return any(token.lower() in ua_lower for token in tokens)


def open_log(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


UA_QUOTED_RE = re.compile(r'"([^"]*)"')


def parse_line(line, ip_field, ua_field):
    """Extract (ip, user_agent) from a log line.

    Default behavior is the NCSA combined log format, where the IP
    is the first whitespace-separated token and the User-Agent is
    the last quoted field. Custom formats can pass explicit field
    indexes.
    """
    tokens = line.split(None, max(ip_field, 1))
    if len(tokens) < ip_field:
        return None
    ip = tokens[ip_field - 1]

    if ua_field is None:
        quoted = UA_QUOTED_RE.findall(line)
        if not quoted:
            return None
        ua = quoted[-1]
    else:
        wide_tokens = line.split()
        if len(wide_tokens) < ua_field:
            return None
        ua = wide_tokens[ua_field - 1]

    return ip, ua


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', required=True, help='Path to access log (plain or .gz)')
    parser.add_argument('--output', help='Write filtered output to this file (default stdout)')
    parser.add_argument(
        '--cache-path', default=DEFAULT_CACHE_PATH,
        help='Where to cache the Googlebot IP ranges JSON',
    )
    parser.add_argument('--refresh-ranges', action='store_true', help='Force refresh of cached IP ranges')
    parser.add_argument(
        '--ip-field', type=int, default=1,
        help='1-indexed whitespace field containing the client IP (default 1)',
    )
    parser.add_argument(
        '--ua-field', type=int, default=None,
        help='1-indexed whitespace field containing the User-Agent. '
             'Default: extract from last quoted field (NCSA combined).',
    )
    parser.add_argument(
        '--strict-googlebot', action='store_true',
        help='Only accept the primary Googlebot token, not the full family',
    )
    parser.add_argument('--summary-only', action='store_true', help='Suppress filtered log output')
    args = parser.parse_args()

    networks = load_googlebot_ranges(args.cache_path, refresh=args.refresh_ranges)
    tokens = STRICT_GOOGLEBOT_TOKENS if args.strict_googlebot else GOOGLEBOT_TOKENS

    stats = Stats()
    rejected_ua_examples = Counter()

    if args.summary_only:
        output_handle = None
    elif args.output:
        output_handle = open(args.output, 'w', encoding='utf-8')
    else:
        output_handle = sys.stdout

    try:
        with open_log(args.log) as f:
            for line in f:
                parsed = parse_line(line, args.ip_field, args.ua_field)
                if parsed is None:
                    stats.unparseable += 1
                    continue
                ip, ua = parsed
                ip_ok = ip_in_networks(ip, networks)
                ua_ok = ua_matches_googlebot(ua, tokens)

                if ip_ok and ua_ok:
                    stats.accepted += 1
                    if output_handle is not None:
                        output_handle.write(line)
                elif not ip_ok and not ua_ok:
                    stats.rejected_both += 1
                elif not ip_ok:
                    stats.rejected_ip += 1
                    if ua_matches_googlebot(ua, GOOGLEBOT_TOKENS):
                        rejected_ua_examples[ua[:120]] += 1
                else:
                    stats.rejected_ua += 1
    finally:
        if output_handle is not None and output_handle is not sys.stdout:
            output_handle.close()

    sys.stderr.write('\nverification summary\n')
    sys.stderr.write('-' * 60 + '\n')
    sys.stderr.write(f'total lines:           {stats.total:>10}\n')
    sys.stderr.write(f'accepted (verified):   {stats.accepted:>10}\n')
    sys.stderr.write(f'rejected (UA spoofed): {stats.rejected_ip:>10}\n')
    sys.stderr.write(f'rejected (wrong UA):   {stats.rejected_ua:>10}\n')
    sys.stderr.write(f'rejected (both fail):  {stats.rejected_both:>10}\n')
    sys.stderr.write(f'unparseable:           {stats.unparseable:>10}\n')

    if rejected_ua_examples:
        sys.stderr.write('\ntop spoofed-UA examples (UA claims Googlebot, IP does not match):\n')
        for ua, count in rejected_ua_examples.most_common(5):
            sys.stderr.write(f'  {count:>6}  {ua}\n')


if __name__ == '__main__':
    main()