#!/usr/bin/env python3
"""
url-normalization.example.py

URL normalization utilities described in Chapter 12 of SEO for
Engineers, Volume 1. Two functions:

    normalize_url(url)
        Sort query parameters alphabetically, lowercase the host
        and path, strip the fragment, and strip a trailing slash
        from non-root paths. Use this when generating canonical
        URLs, sitemap entries, or internal links so the same logical
        URL always serializes the same way.

    strip_insignificant_params(url)
        Drop tracking, session, and analytics parameters from a
        URL while preserving the rest. Use this on URLs read from
        Referer headers, share-button events, or any source where
        marketing parameters may have been appended.

The two functions are independent. Normalize first, then strip if
needed, or strip first if you want the unsorted clean URL.

Run this file directly to see the smoke-test output.

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Parameters known to track marketing/analytics state rather than
# select content. Extend per-site as new tracking systems appear.
INSIGNIFICANT_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term",
    "utm_content", "fbclid", "gclid", "msclkid", "ref",
    "sessionid", "sid", "source", "mc_cid", "mc_eid",
    "_ga", "_gl", "yclid", "scid",
})


def normalize_url(url: str) -> str:
    """
    Reduce a URL to a canonical form by:
      - Lowercasing the scheme and host (RFC 3986 says these are
        case-insensitive).
      - Sorting query parameters alphabetically by key, and within
        each key, sorting multi-values lexically.
      - Stripping a trailing slash from non-root paths.
      - Stripping the fragment (Google and other crawlers ignore it).

    The path itself is NOT lowercased. Path case is significant in
    RFC 3986 and most filesystems on Linux are case-sensitive. If
    your site enforces lowercase paths, do that with server-level
    middleware (see lowercase-url-middleware patterns in the
    chapter), not here.
    """
    parsed = urlparse(url)

    # parse_qsl preserves the relative order of multi-values within
    # the same key. Sort each value list independently so
    # ?tag=z&tag=a normalizes the same as ?tag=a&tag=z.
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    grouped: dict[str, list[str]] = {}
    for k, v in pairs:
        grouped.setdefault(k, []).append(v)
    for k in grouped:
        grouped[k].sort()

    sorted_pairs = [
        (k, v) for k in sorted(grouped) for v in grouped[k]
    ]
    normalized_query = urlencode(sorted_pairs)

    # Strip trailing slash from non-root paths. The "or '/'" guard
    # preserves the root URL.
    path = parsed.path.rstrip("/") or "/"

    return urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        parsed.params,
        normalized_query,
        "",  # Strip fragment.
    ))


def strip_insignificant_params(url: str) -> str:
    """
    Remove tracking, session, and analytics parameters from a URL
    while preserving everything else. The comparison is
    case-insensitive on the parameter name.
    """
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    significant = [
        (k, v) for k, v in pairs
        if k.lower() not in INSIGNIFICANT_PARAMS
    ]
    clean_query = urlencode(significant)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        clean_query,
        "",
    ))


if __name__ == "__main__":
    cases = [
        # Sorted parameters, lowercased host, fragment stripped.
        "https://EXAMPLE.com/Products?color=red&category=shoes#reviews",
        # Trailing slash stripped from non-root path.
        "https://example.com/products/",
        # Root slash preserved.
        "https://example.com/",
        # Multi-value parameter, sorted internally.
        "https://example.com/blog?tag=z&tag=a&tag=m",
        # Tracking parameters mixed with real ones.
        "https://example.com/products?category=shoes&utm_source=email&fbclid=abc",
    ]

    print("normalize_url:")
    for url in cases:
        print(f"  {url}")
        print(f"    -> {normalize_url(url)}")

    print("\nstrip_insignificant_params:")
    tracking_cases = [
        "https://example.com/products?category=shoes&utm_source=email",
        "https://example.com/article?fbclid=abc&gclid=xyz&id=42",
        "https://example.com/page?ref=twitter&utm_campaign=launch",
    ]
    for url in tracking_cases:
        print(f"  {url}")
        print(f"    -> {strip_insignificant_params(url)}")
