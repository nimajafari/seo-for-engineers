#!/usr/bin/env python3
"""
parse_logs.py

Log format converter for SEO log analysis. Reads NCSA Combined,
nginx default, nginx JSON, Apache, AWS ALB, and Cloudflare Logpush
formats and emits a normalized JSON Lines stream.

The normalized schema is the union of fields Chapter 18 references
across its analytical queries: timestamp, remote_addr, method, host,
uri, path, status, bytes_sent, referer, user_agent, request_time.

Bad lines are logged to stderr with the original content; the
script continues processing the rest of the file.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime, timezone

NCSA_COMBINED_RE = re.compile(
    r'^(?P<remote_addr>\S+)\s+\S+\s+\S+\s+'
    r'\[(?P<timestamp>[^\]]+)\]\s+'
    r'"(?P<method>\S+)\s+(?P<uri>\S+)\s+HTTP/[\d.]+"\s+'
    r'(?P<status>\d+)\s+(?P<bytes_sent>\S+)\s+'
    r'"(?P<referer>[^"]*)"\s+"(?P<user_agent>[^"]*)"'
    r'(?:\s+(?P<request_time>\S+))?'
)

NCSA_TIMESTAMP_FORMAT = '%d/%b/%Y:%H:%M:%S %z'

ALB_FIELD_INDEX = {
    'timestamp': 1,
    'elb': 2,
    'client_ip_port': 3,
    'target_ip_port': 4,
    'request_processing_time': 5,
    'target_processing_time': 6,
    'response_processing_time': 7,
    'elb_status_code': 8,
    'target_status_code': 9,
    'received_bytes': 10,
    'sent_bytes': 11,
    'request': 12,
    'user_agent': 13,
}


def open_input(path: str):
    if path == '-':
        return sys.stdin
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8', errors='replace')
    return open(path, 'r', encoding='utf-8', errors='replace')


def normalize_timestamp(raw: str, fmt: str | None = None) -> str:
    if fmt:
        dt = datetime.strptime(raw, fmt)
    elif 'T' in raw:
        dt = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    else:
        dt = datetime.strptime(raw, NCSA_TIMESTAMP_FORMAT)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def extract_path(uri: str) -> str:
    return uri.split('?', 1)[0]


def parse_combined(line: str) -> dict | None:
    match = NCSA_COMBINED_RE.match(line.strip())
    if not match:
        return None
    fields = match.groupdict()
    uri = fields['uri']
    try:
        return {
            'timestamp': normalize_timestamp(fields['timestamp'],
                                             NCSA_TIMESTAMP_FORMAT),
            'remote_addr': fields['remote_addr'],
            'method': fields['method'],
            'host': '',
            'uri': uri,
            'path': extract_path(uri),
            'status': int(fields['status']),
            'bytes_sent': (int(fields['bytes_sent'])
                           if fields['bytes_sent'].isdigit() else 0),
            'referer': fields['referer'],
            'user_agent': fields['user_agent'],
            'request_time': (float(fields['request_time'])
                             if fields['request_time'] else None),
        }
    except (ValueError, KeyError):
        return None


def parse_nginx_json(line: str) -> dict | None:
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None

    try:
        uri = record.get('uri') or record.get('request_uri', '')
        return {
            'timestamp': normalize_timestamp(record['timestamp']),
            'remote_addr': record.get('remote_addr', ''),
            'method': record.get('method', ''),
            'host': record.get('host', ''),
            'uri': uri,
            'path': extract_path(uri),
            'status': int(record.get('status', 0)),
            'bytes_sent': int(record.get('bytes_sent', 0)),
            'referer': record.get('referer', ''),
            'user_agent': record.get('user_agent', ''),
            'request_time': (float(record['request_time'])
                             if record.get('request_time') else None),
        }
    except (ValueError, KeyError):
        return None


def parse_cloudflare(line: str) -> dict | None:
    """Cloudflare Logpush HTTP request format."""
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return None

    try:
        ts_raw = (record.get('EdgeStartTimestamp')
                  or record.get('datetime')
                  or record.get('timestamp', ''))
        if isinstance(ts_raw, (int, float)):
            dt = datetime.fromtimestamp(ts_raw / 1e9 if ts_raw > 1e12
                                        else ts_raw, tz=timezone.utc)
            ts = dt.isoformat()
        else:
            ts = normalize_timestamp(str(ts_raw))

        uri = (record.get('ClientRequestURI')
               or record.get('clientrequesturi', ''))
        return {
            'timestamp': ts,
            'remote_addr': (record.get('ClientIP')
                            or record.get('clientip', '')),
            'method': (record.get('ClientRequestMethod')
                       or record.get('clientrequesthttpmethodname', '')),
            'host': (record.get('ClientRequestHost')
                     or record.get('clientrequesthost', '')),
            'uri': uri,
            'path': extract_path(uri),
            'status': int(record.get('EdgeResponseStatus')
                          or record.get('edgeresponsestatus', 0)),
            'bytes_sent': int(record.get('EdgeResponseBytes')
                              or record.get('bytes', 0)),
            'referer': (record.get('ClientRequestReferer')
                        or record.get('referer', '')),
            'user_agent': (record.get('ClientRequestUserAgent')
                           or record.get('useragent', '')),
            'request_time': None,
        }
    except (ValueError, KeyError):
        return None


def parse_alb(line: str) -> dict | None:
    """AWS ALB access log format."""
    # ALB logs are space-separated with quoted strings.
    # Use a simple state-machine split.
    tokens = []
    current = []
    in_quote = False
    for ch in line.strip():
        if ch == '"':
            in_quote = not in_quote
        elif ch == ' ' and not in_quote:
            tokens.append(''.join(current))
            current = []
            continue
        current.append(ch)
    if current:
        tokens.append(''.join(current))

    if len(tokens) < 13:
        return None

    try:
        client_ip = tokens[2].split(':')[0]
        request = tokens[11].strip('"')
        request_parts = request.split(' ', 2)
        method = request_parts[0] if request_parts else ''
        uri = request_parts[1] if len(request_parts) > 1 else ''

        target_time = tokens[5]
        return {
            'timestamp': normalize_timestamp(tokens[1]),
            'remote_addr': client_ip,
            'method': method,
            'host': '',
            'uri': uri,
            'path': extract_path(uri),
            'status': int(tokens[7]) if tokens[7].isdigit() else 0,
            'bytes_sent': (int(tokens[10])
                           if tokens[10].isdigit() else 0),
            'referer': '',
            'user_agent': tokens[12].strip('"') if len(tokens) > 12 else '',
            'request_time': (float(target_time)
                             if target_time != '-1' else None),
        }
    except (ValueError, IndexError):
        return None


PARSERS = {
    'combined': parse_combined,
    'apache': parse_combined,  # same format
    'nginx': parse_combined,
    'nginx_json': parse_nginx_json,
    'cloudflare': parse_cloudflare,
    'alb': parse_alb,
}


def detect_format(sample_line: str) -> str:
    stripped = sample_line.strip()
    if stripped.startswith('{'):
        try:
            record = json.loads(stripped)
        except json.JSONDecodeError:
            return 'combined'
        if 'EdgeStartTimestamp' in record or 'ClientIP' in record:
            return 'cloudflare'
        return 'nginx_json'
    if 'app/' in stripped and ' http ' in stripped.lower():
        return 'alb'
    return 'combined'


def process(input_path: str, output_path: str | None,
            fmt: str | None) -> dict:
    stats = {'accepted': 0, 'rejected': 0}
    output_handle = (open(output_path, 'w', encoding='utf-8')
                     if output_path else sys.stdout)

    try:
        with open_input(input_path) as f:
            first_line = None
            if fmt is None:
                first_line = f.readline()
                if not first_line:
                    return stats
                fmt = detect_format(first_line)
                sys.stderr.write(f'autodetected format: {fmt}\n')

            parser = PARSERS.get(fmt)
            if parser is None:
                raise ValueError(f'unknown format: {fmt}')

            if first_line is not None:
                record = parser(first_line)
                if record:
                    output_handle.write(json.dumps(record) + '\n')
                    stats['accepted'] += 1
                else:
                    stats['rejected'] += 1
                    sys.stderr.write(f'bad line: {first_line[:200]}\n')

            for line in f:
                if not line.strip():
                    continue
                record = parser(line)
                if record:
                    output_handle.write(json.dumps(record) + '\n')
                    stats['accepted'] += 1
                else:
                    stats['rejected'] += 1
                    if stats['rejected'] < 10:
                        sys.stderr.write(f'bad line: {line[:200]}\n')
    finally:
        if output_path:
            output_handle.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True,
                        help='Path to input log file, .gz supported, '
                             '- for stdin')
    parser.add_argument('--output', help='Output path, stdout if omitted')
    parser.add_argument('--format', choices=sorted(PARSERS.keys()),
                        help='Input format, autodetected if omitted')
    args = parser.parse_args()

    stats = process(args.input, args.output, args.format)

    sys.stderr.write('\nparse summary\n')
    sys.stderr.write('-' * 40 + '\n')
    sys.stderr.write(f'accepted: {stats["accepted"]}\n')
    sys.stderr.write(f'rejected: {stats["rejected"]}\n')

    sys.exit(0 if stats['accepted'] > 0 else 1)


if __name__ == '__main__':
    main()