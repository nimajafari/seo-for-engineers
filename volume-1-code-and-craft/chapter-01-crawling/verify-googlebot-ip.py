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
    python3 verify-googlebot-ip.py <ip>

Exits 0 if the IP is in a published range, 1 otherwise.

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

GOOGLEBOT_RANGES_URL = (
    "https://developers.google.com/static/search/apis/ipranges/googlebot.json"
)
COMMON_CRAWLERS_URL = (
    "https://developers.google.com/static/crawling/ipranges/common-crawlers.json"
)

SOURCES = {
    "googlebot": GOOGLEBOT_RANGES_URL,
    "common-crawlers": COMMON_CRAWLERS_URL,
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


def ip_in_ranges(ip: str, ranges: list[str]) -> bool:
    """Return True if the IP falls inside any of the CIDR ranges."""
    target = ipaddress.ip_address(ip)
    for cidr in ranges:
        if cidr and target in ipaddress.ip_network(cidr):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ip", help="IP address to check")
    args = parser.parse_args()

    context = build_ssl_context()

    for name, url in SOURCES.items():
        try:
            ranges = fetch_ranges(url, context)
        except Exception as exc:
            print(f"Could not fetch {name} ranges: {exc}", file=sys.stderr)
            continue
        if ip_in_ranges(args.ip, ranges):
            print(f"OK, {args.ip} is in the {name} range list")
            return 0

    print(f"{args.ip} is not in any published Google crawler IP range")
    return 1


if __name__ == "__main__":
    sys.exit(main())