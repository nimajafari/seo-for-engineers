#!/usr/bin/env python3
"""
enrich_logs.py

The DuckDB enrichment pipeline from Chapter 18 section 18.4.2,
productized. Reads normalized JSON Lines (the output of
parse_logs.py), verifies crawler identity by IP against published
IP ranges, extracts the path from the URI, anonymizes IPs after
verification, and writes ZSTD-compressed Parquet.

The enrich-once-query-many pattern the chapter argues for.
"""

from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import os
import sys

import duckdb

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    'verify_crawler', os.path.join(THIS_DIR, 'verify_crawler.py')
)
VC = importlib.util.module_from_spec(SPEC)
# Register before exec_module so dataclass introspection (which reads
# sys.modules[cls.__module__] on Python 3.14+) can resolve the module.
sys.modules['verify_crawler'] = VC
SPEC.loader.exec_module(VC)


def anonymize_ip(ip_str: str) -> str:
    """Truncate the last octet of IPv4 or last 80 bits of IPv6."""
    if not ip_str:
        return ''
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return ''
    if isinstance(ip, ipaddress.IPv4Address):
        parts = ip_str.split('.')
        return '.'.join(parts[:3] + ['0'])
    # IPv6: keep first 48 bits (3 hextets), zero the rest.
    expanded = ip.exploded.split(':')
    return ':'.join(expanded[:3] + ['0'] * 5)


def build_verifier(crawler_filter: list | None):
    crawlers = VC.load_all_crawlers(crawler_filter)
    purpose_lookup = {
        name: c.purpose for name, c in crawlers.items()
    }

    def verify(ip_str: str) -> str:
        if not ip_str:
            return ''
        crawler = VC.classify_ip(ip_str, crawlers)
        return crawler or ''

    def purpose(crawler: str) -> str:
        return purpose_lookup.get(crawler, '')

    return verify, purpose


def _sql_quote(value: str) -> str:
    """SQL string-literal escape for paths that we have to embed
    directly into COPY ... TO and read_json_auto(), neither of which
    accepts parameter binding."""
    return value.replace("'", "''")


def enrich(input_glob: str, output_path: str,
           crawler_filter: list | None,
           anonymize: bool) -> None:
    con = duckdb.connect(':memory:')

    verify, purpose = build_verifier(crawler_filter)
    con.create_function('verify_crawler', verify, ['VARCHAR'], 'VARCHAR')
    con.create_function('crawler_purpose', purpose, ['VARCHAR'], 'VARCHAR')

    if anonymize:
        con.create_function('anonymize_ip', anonymize_ip,
                            ['VARCHAR'], 'VARCHAR')
        ip_expr = 'anonymize_ip(remote_addr)'
    else:
        ip_expr = 'remote_addr'

    sys.stderr.write(f'reading from: {input_glob}\n')
    sys.stderr.write(f'writing to:   {output_path}\n')
    sys.stderr.write(f'anonymize:    {anonymize}\n\n')

    input_sql = _sql_quote(input_glob)
    output_sql = _sql_quote(output_path)

    # CTE so verify_crawler() is invoked once per row instead of
    # three times (once for the column, once for crawler_purpose,
    # once for the verified_googlebot flag).
    con.execute(f"""
        COPY (
            WITH typed AS (
                SELECT
                    CAST(timestamp AS TIMESTAMP) AS timestamp,
                    {ip_expr} AS remote_addr,
                    method,
                    host,
                    uri,
                    regexp_extract(uri, '^([^?]+)', 1) AS path,
                    status,
                    bytes_sent,
                    user_agent,
                    request_time,
                    verify_crawler(remote_addr) AS verified_crawler
                FROM read_json_auto('{input_sql}')
            )
            SELECT
                timestamp,
                remote_addr,
                method,
                host,
                uri,
                path,
                status,
                bytes_sent,
                user_agent,
                request_time,
                verified_crawler,
                crawler_purpose(verified_crawler) AS crawler_purpose,
                verified_crawler IN ('googlebot', 'special-crawlers')
                    AS verified_googlebot
            FROM typed
        )
        TO '{output_sql}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """)

    summary = con.execute(f"""
        SELECT
            COUNT(*) AS total_requests,
            COUNT(*) FILTER (WHERE verified_crawler != '') AS verified_crawlers,
            COUNT(DISTINCT verified_crawler) FILTER
                (WHERE verified_crawler != '') AS distinct_crawler_types
        FROM read_parquet('{output_sql}')
    """).fetchone()

    crawler_breakdown = con.execute(f"""
        SELECT verified_crawler, COUNT(*) AS requests
        FROM read_parquet('{output_sql}')
        WHERE verified_crawler != ''
        GROUP BY verified_crawler
        ORDER BY requests DESC
    """).fetchall()

    sys.stderr.write('enrichment summary\n')
    sys.stderr.write('-' * 50 + '\n')
    sys.stderr.write(f'total requests:        {summary[0]}\n')
    sys.stderr.write(f'verified crawlers:     {summary[1]}\n')
    sys.stderr.write(f'distinct crawler types: {summary[2]}\n')
    if crawler_breakdown:
        sys.stderr.write('\nby crawler:\n')
        for crawler, count in crawler_breakdown:
            sys.stderr.write(f'  {crawler:25s} {count:>10}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True,
                        help='Input glob, e.g. logs/raw/access-*.ndjson')
    parser.add_argument('--output', required=True,
                        help='Output Parquet file path')
    parser.add_argument('--crawlers',
                        help='Comma-separated subset of crawler names')
    parser.add_argument('--no-anonymize', action='store_true',
                        help='Keep full IP addresses (default: anonymize)')
    args = parser.parse_args()

    crawler_filter: list | None = (
        args.crawlers.split(',') if args.crawlers else None
    )

    enrich(args.input, args.output, crawler_filter,
           anonymize=not args.no_anonymize)


if __name__ == '__main__':
    main()