#!/usr/bin/env python3
"""
verify-googlebot-ip.py

Verify whether an IP belongs to a published Google crawler range.

This is the modern approach for verifying Googlebot at scale. Instead of
running a reverse DNS lookup per request, match the connecting IP against
Google's published JSON files of crawler IP ranges. The JSON files are
maintained by Google. For production use, cache them locally and refresh
on a schedule rather than calling the endpoints on every request.

Usage:
    python verify-googlebot-ip.py <ip>

Range lists checked:
    common-crawlers   Googlebot and the other crawlers that obey robots.txt
                      (the old googlebot.json URL now redirects here)
    special-crawlers  crawlers such as AdsBot that may ignore robots.txt

User-triggered fetchers (user-triggered-fetchers*.json) are deliberately
not checked: they act on behalf of a user, not as crawlers.

Exit codes:
    0  the IP is in a published Google crawler range
    1  the IP is not in any published range (every range list was fetched)
    2  indeterminate: a range list could not be fetched and none of the
       lists that were fetched matched (a transient network failure must
       not be read as "not Googlebot"), or the argument is not a valid IP

macOS note: if you see "SSL: CERTIFICATE_VERIFY_FAILED", the Python.org
installer does not register with the system trust store. Fix with either:

    pip install certifi
    pip3 install certifi

or run the bundled certificate installer that ships with Python.org builds:

    /Applications/Python\\ 3.x/Install\\ Certificates.command

This script will automatically use certifi's CA bundle if it is installed.

Reference: SEO for Engineers, Volume 1, Chapter 1.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import ssl
import sys
import urllib.request

# Google moved these files under /static/crawling/ipranges/. The old
# /static/search/apis/ipranges/googlebot.json URL now 301-redirects to
# common-crawlers.json, so listing both would fetch the same list twice.
COMMON_CRAWLERS_URL = (
    "https://developers.google.com/static/crawling/ipranges/common-crawlers.json"
)
SPECIAL_CRAWLERS_URL = (
    "https://developers.google.com/static/crawling/ipranges/special-crawlers.json"
)

SOURCES = {
    "common-crawlers": COMMON_CRAWLERS_URL,
    "special-crawlers": SPECIAL_CRAWLERS_URL,
}


def build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context that uses certifi's CA bundle when available.

    On macOS, the Python.org installer ships without registering with the
    system trust store, which causes CERTIFICATE_VERIFY_FAILED errors. If
    certifi is installed, point OpenSSL at its bundled roots.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_ranges(url: str, context: ssl.SSLContext) -> list[str]:
    """Fetch and parse a Google IP-ranges JSON file."""
    with urllib.request.urlopen(url, timeout=10, context=context) as resp:
        data = json.load(resp)
    return [
        prefix.get("ipv6Prefix") or prefix.get("ipv4Prefix")
        for prefix in data.get("prefixes", [])
    ]


def parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Parse an IP address, unwrapping IPv4-mapped IPv6 (::ffff:a.b.c.d).

    Dual-stack servers often log IPv4 clients in the mapped form. Google
    publishes those ranges as plain IPv4 prefixes, and an IPv6 address is
    never "in" an IPv4 network, so without unwrapping a genuine Googlebot
    hit would be reported as not Googlebot.
    """
    addr = ipaddress.ip_address(value.strip())
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return addr.ipv4_mapped
    return addr


def ip_in_ranges(ip: str, ranges: list[str]) -> bool:
    """Return True if the IP falls inside any of the CIDR ranges."""
    target = parse_ip(ip)
    for cidr in ranges:
        if cidr and target in ipaddress.ip_network(cidr):
            return True
    return False


def ip_argument(value: str) -> str:
    """argparse type: reject a malformed IP with a usage error, not a traceback."""
    try:
        parse_ip(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a valid IP address: {value!r}")
    return value.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("ip", type=ip_argument, help="IP address to check")
    args = parser.parse_args()

    context = build_ssl_context()

    failed: list[str] = []
    for name, url in SOURCES.items():
        try:
            ranges = fetch_ranges(url, context)
        except Exception as exc:
            print(f"Could not fetch {name} ranges: {exc}", file=sys.stderr)
            failed.append(name)
            continue
        if ip_in_ranges(args.ip, ranges):
            print(f"OK, {args.ip} is in the {name} range list")
            return 0

    # A list that could not be fetched might have contained the IP, so a
    # miss is only conclusive when every list was checked. Returning a
    # distinct code keeps a transient outage from being misread as "this
    # IP is not Googlebot" by a calling gate.
    if failed:
        print(
            f"Could not fetch {', '.join(failed)} range list(s) and no other "
            f"list matched; verification of {args.ip} is indeterminate",
            file=sys.stderr,
        )
        return 2

    print(f"{args.ip} is not in any published Google crawler IP range")
    return 1


if __name__ == "__main__":
    sys.exit(main())