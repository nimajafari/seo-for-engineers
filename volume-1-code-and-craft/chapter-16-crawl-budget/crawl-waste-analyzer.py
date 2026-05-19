#!/usr/bin/env python3
"""
crawl-waste-analyzer.py

Consume a verified Googlebot log (typically the output of
verify-googlebot.py) and produce the standard crawl-waste diagnostic
report from Chapter 16 of SEO for Engineers, Volume 1.

The script materializes in code what the chapter's three awk queries
describe in shell, plus four further analyses the chapter calls out
as worth tracking on every run:

  1. Status code distribution (200 / 304 / 404 / 410 / 3xx / 5xx).
  2. Top URL patterns by crawl volume, query strings stripped.
  3. Parameter frequency across all crawled URLs.
  4. Asset-path crawl share (CSS, JS, image, framework chunks).
  5. Soft-404 candidates (200 with response size below threshold).
  6. Redirect-chain ratio (per-pattern 3xx / total).
  7. Per-URL-pattern TTFB p50 and p95 (if response times are present).

Output is JSON. A human-readable summary is also written to stderr.
The script makes no policy recommendations; it produces the data the
chapter's decision framework operates on.
"""

import argparse
import gzip
import json
import math
import re
import sys
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass, field

DEFAULT_SOFT_404_THRESHOLD = 1024
DEFAULT_TOP_PATTERNS = 50
DEFAULT_TOP_PARAMETERS = 50

ASSET_PATH_RE = re.compile(
    r'\.(?:css|js|mjs|map|png|jpe?g|gif|svg|webp|avif|ico|woff2?|ttf|otf|eot)'
    r'(?:[?#]|$)',
    re.IGNORECASE,
)
ASSET_DIR_RE = re.compile(
    r'^/(?:static|assets|_next|_nuxt|build|dist|public|cdn)/',
    re.IGNORECASE,
)

QUOTED_RE = re.compile(r'"([^"]*)"')


@dataclass
class PatternStats:
    requests: int = 0
    bytes_total: int = 0
    status_counts: Counter = field(default_factory=Counter)
    response_times: list = field(default_factory=list)


def open_log(path):
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


def parse_line(line, status_field, url_field, size_field, rtime_field):
    """
    Extract (status, url, size, response_time) from a log line.

    Defaults assume NCSA combined log format with response time
    appended:
      $remote_addr - - [$time_local] "$request" $status $body_bytes
      "$referrer" "$user_agent" $request_time

    The URL is the second token inside the quoted request string
    ("METHOD URL HTTP/1.1"). All other fields are whitespace-tokenized.
    """
    tokens = line.split()
    if len(tokens) < max(status_field, url_field, size_field):
        return None

    quoted = QUOTED_RE.findall(line)
    if not quoted:
        return None

    url = None
    for q in quoted:
        parts = q.split()
        if len(parts) >= 2 and parts[0].isupper() and parts[0].isalpha():
            url = parts[1]
            break
    if url is None and url_field is not None:
        try:
            url = tokens[url_field - 1]
        except IndexError:
            return None
    if url is None:
        return None

    try:
        status = int(tokens[status_field - 1])
    except (ValueError, IndexError):
        return None

    size = 0
    try:
        raw_size = tokens[size_field - 1]
        if raw_size not in ('-', ''):
            size = int(raw_size)
    except (ValueError, IndexError):
        size = 0

    rtime = None
    if rtime_field is not None:
        try:
            rtime = float(tokens[rtime_field - 1])
        except (ValueError, IndexError):
            rtime = None

    return status, url, size, rtime


def url_pattern(url):
    """
    Strip query string and fragment for pattern aggregation. Leaves
    the path alone; faceted-aggregation (per-segment templating) is
    Chapter 17's concern, not chapter 16's.
    """
    parsed = urllib.parse.urlsplit(url)
    return parsed.path or '/'


def parameters(url):
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return []
    return [name for name, _ in urllib.parse.parse_qsl(
        parsed.query, keep_blank_values=True
    )]


def is_asset(url):
    path = url_pattern(url)
    return bool(ASSET_PATH_RE.search(path) or ASSET_DIR_RE.match(path))


def status_bucket(status):
    if status == 200:
        return '200'
    if status == 304:
        return '304'
    if status == 404:
        return '404'
    if status == 410:
        return '410'
    if 300 <= status < 400:
        return '3xx'
    if 500 <= status < 600:
        return '5xx'
    if 200 <= status < 300:
        return '2xx_other'
    if 400 <= status < 500:
        return '4xx_other'
    return 'other'


def percentile(values, p):
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return ordered[int(k)]
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def analyze(args):
    status_counter = Counter()
    pattern_stats: dict[str, PatternStats] = defaultdict(PatternStats)
    parameter_counter = Counter()
    soft_404_candidates = []
    asset_requests = 0
    total_requests = 0
    unparseable = 0

    with open_log(args.log) as f:
        for line in f:
            parsed = parse_line(
                line, args.status_field, args.url_field,
                args.size_field, args.rtime_field,
            )
            if parsed is None:
                unparseable += 1
                continue
            status, url, size, rtime = parsed
            total_requests += 1

            bucket = status_bucket(status)
            status_counter[bucket] += 1

            pattern = url_pattern(url)
            stats = pattern_stats[pattern]
            stats.requests += 1
            stats.bytes_total += size
            stats.status_counts[bucket] += 1
            if rtime is not None:
                stats.response_times.append(rtime)

            for param in parameters(url):
                parameter_counter[param] += 1

            if is_asset(url):
                asset_requests += 1

            if status == 200 and size and size < args.soft_404_threshold:
                soft_404_candidates.append({
                    'url': url,
                    'size': size,
                })

    top_patterns = sorted(
        pattern_stats.items(), key=lambda kv: kv[1].requests, reverse=True,
    )[: args.top_patterns]

    top_pattern_report = []
    for pattern, stats in top_patterns:
        entry = {
            'pattern': pattern,
            'requests': stats.requests,
            'share': stats.requests / total_requests if total_requests else 0,
            'status_breakdown': dict(stats.status_counts),
            'redirect_ratio': (
                (stats.status_counts.get('3xx', 0) / stats.requests)
                if stats.requests else 0
            ),
        }
        if stats.response_times:
            entry['ttfb_p50'] = percentile(stats.response_times, 50)
            entry['ttfb_p95'] = percentile(stats.response_times, 95)
        top_pattern_report.append(entry)

    top_parameter_report = [
        {'parameter': p, 'count': c}
        for p, c in parameter_counter.most_common(args.top_parameters)
    ]

    soft_404_report = sorted(
        soft_404_candidates, key=lambda x: x['size']
    )[:200]

    report = {
        'totals': {
            'requests': total_requests,
            'unparseable': unparseable,
        },
        'status_distribution': {
            bucket: {
                'count': count,
                'share': count / total_requests if total_requests else 0,
            }
            for bucket, count in status_counter.most_common()
        },
        'asset_share': {
            'requests': asset_requests,
            'share': asset_requests / total_requests if total_requests else 0,
        },
        'top_patterns': top_pattern_report,
        'top_parameters': top_parameter_report,
        'soft_404_candidates': soft_404_report,
    }

    return report


def write_summary(report, stream):
    totals = report['totals']
    stream.write('\ncrawl-waste summary\n')
    stream.write('-' * 60 + '\n')
    stream.write(f'total requests:    {totals["requests"]:>10}\n')
    stream.write(f'unparseable lines: {totals["unparseable"]:>10}\n')

    stream.write('\nstatus distribution\n')
    for bucket, info in report['status_distribution'].items():
        stream.write(
            f'  {bucket:>10}  {info["count"]:>10}  {info["share"] * 100:>6.2f}%\n'
        )

    asset = report['asset_share']
    stream.write(
        f'\nasset share:       {asset["requests"]:>10}  '
        f'{asset["share"] * 100:>6.2f}%\n'
    )

    stream.write('\ntop 10 URL patterns by crawl volume\n')
    for entry in report['top_patterns'][:10]:
        line = (
            f'  {entry["requests"]:>8}  '
            f'{entry["share"] * 100:>5.2f}%  '
            f'redir={entry["redirect_ratio"] * 100:>5.1f}%  '
            f'{entry["pattern"]}\n'
        )
        stream.write(line)

    stream.write('\ntop 10 parameters\n')
    for entry in report['top_parameters'][:10]:
        stream.write(f'  {entry["count"]:>8}  {entry["parameter"]}\n')

    candidates = report['soft_404_candidates']
    stream.write(f'\nsoft-404 candidates: {len(candidates)}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', required=True,
                        help='Path to verified Googlebot log (plain or .gz)')
    parser.add_argument('--output',
                        help='Write JSON report to this file (default stdout)')
    parser.add_argument('--top-patterns', type=int,
                        default=DEFAULT_TOP_PATTERNS,
                        help='Number of URL patterns to report')
    parser.add_argument('--top-parameters', type=int,
                        default=DEFAULT_TOP_PARAMETERS,
                        help='Number of URL parameters to report')
    parser.add_argument('--soft-404-threshold', type=int,
                        default=DEFAULT_SOFT_404_THRESHOLD,
                        help='Body-size threshold (bytes) for soft-404 flagging')
    parser.add_argument('--status-field', type=int, default=9,
                        help='1-indexed field containing the HTTP status code')
    parser.add_argument('--url-field', type=int, default=7,
                        help='1-indexed field containing the URL (fallback '
                             'if the quoted request line is unparseable)')
    parser.add_argument('--size-field', type=int, default=10,
                        help='1-indexed field containing the response size')
    parser.add_argument('--rtime-field', type=int, default=None,
                        help='1-indexed field containing the response time. '
                             'If unset, TTFB percentiles are omitted.')
    args = parser.parse_args()

    report = analyze(args)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
    else:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write('\n')

    write_summary(report, sys.stderr)


if __name__ == '__main__':
    main()
