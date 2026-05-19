#!/usr/bin/env python3
"""
check_robots_facets.py

Faceted-navigation-specific robots.txt CI check from Chapter 17.

Asserts that a list of business-critical category and product URLs
remain crawlable by Googlebot, and that a list of tracking-only and
session-only URL patterns remain blocked. This is the minimum
defensive check for any deploy that touches robots.txt on a site
with faceted navigation.

For broader robots.txt validation including catch-all-Disallow
detection, asset-path blocking, and assertion-suite formats, see
the Chapter 15 tooling at
volume-1-code-and-craft/chapter-15-robots-txt/robots-ci-check.py.

Usage:
    python check_robots_facets.py https://www.example.com/robots.txt

Exit code 0 if all assertions pass, 1 otherwise.
"""

import sys
import urllib.robotparser

# URLs that MUST remain crawlable for indexing to work.
# Extend this list with every Tier 1 URL pattern in your site.
CRITICAL_URLS = [
    "https://www.example.com/",
    "https://www.example.com/category/shoes",
    "https://www.example.com/category/shoes/running",
    "https://www.example.com/product/nike-pegasus-41",
    "https://www.example.com/size-10-running-shoes",
    # Curated Tier 1 facet promotions, if you use path-based facets
    "https://www.example.com/category/shoes/black",
    "https://www.example.com/category/shoes/red",
    # Critical static assets needed for rendering
    "https://www.example.com/static/app.css",
    "https://www.example.com/static/app.js",
]

# URLs that MUST remain blocked. These are the Tier 4 patterns
# from the chapter: session, tracking, and infinite-combination
# parameters that have zero indexing value and zero link equity.
BLOCKED_URLS = [
    "https://www.example.com/category/shoes?sessionid=abc123",
    "https://www.example.com/category/shoes?sid=xyz",
    "https://www.example.com/category/shoes?utm_source=facebook",
    "https://www.example.com/category/shoes?utm_campaign=spring",
    "https://www.example.com/category/shoes?gclid=Cj0KCQ",
    "https://www.example.com/category/shoes?fbclid=IwAR",
    "https://www.example.com/category/shoes?price_min=43&price_max=179",
    "https://www.example.com/search?q=running+shoes",
]


def check_robots(robots_txt_url: str) -> bool:
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_txt_url)
    rp.read()

    ok = True
    for url in CRITICAL_URLS:
        if not rp.can_fetch("Googlebot", url):
            print(f"FAIL: {url} is blocked but should be crawlable")
            ok = False
    for url in BLOCKED_URLS:
        if rp.can_fetch("Googlebot", url):
            print(f"FAIL: {url} is crawlable but should be blocked")
            ok = False

    if ok:
        print(f"OK: {len(CRITICAL_URLS)} crawlable, "
              f"{len(BLOCKED_URLS)} blocked, all assertions passed")
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: check_robots_facets.py <robots.txt URL>", file=sys.stderr)
        sys.exit(2)
    sys.exit(0 if check_robots(sys.argv[1]) else 1)