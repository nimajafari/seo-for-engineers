"""
example_slug_implementation.py

A reference slug-generation implementation that the test suite in
this directory exercises by default. This is the same algorithm
shown inline in Chapter 12, packaged for import.

This module exists so that `slug-generator-test-suite.py` can be
run as a smoke test against a known-passing implementation. To
test your own slug generator, point the test suite at your module
with --module and --function.

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Callable, Optional

try:
    from unidecode import unidecode
    HAS_UNIDECODE = True
except ImportError:
    HAS_UNIDECODE = False


RESERVED_SLUGS = frozenset({
    "admin", "api", "static", "assets", "login", "logout", "register",
    "search", "feed", "sitemap", "robots", "favicon", "null",
    "undefined", "new", "edit", "delete", "settings", "profile",
    "account", "help", "support", "about", "contact", "privacy",
    "terms", "status", "health", "metrics",
})

FALLBACK_SLUG = "untitled"


def generate_slug(
    title: str,
    max_length: int = 80,
    exists_fn: Optional[Callable[[str], bool]] = None,
) -> str:
    """
    Generate a URL-safe slug from a title string.

    Handles Unicode normalization, transliteration, reserved-word
    protection, length truncation at word boundaries, and collision
    resolution via sequential suffixes.

    Args:
        title: Human-readable title to slugify.
        max_length: Maximum slug length.
        exists_fn: Callable that returns True if the slug already
                   exists. Used for collision resolution.

    Returns:
        A lowercase, hyphen-separated, URL-safe slug string.
    """
    # Step 1, transliterate non-ASCII characters if unidecode is
    # available. Falls back to NFKD diacritic stripping otherwise.
    if HAS_UNIDECODE:
        ascii_text = unidecode(title or "")
    else:
        normalized = unicodedata.normalize("NFKD", title or "")
        ascii_text = "".join(
            c for c in normalized if not unicodedata.combining(c)
        )

    # Step 2, lowercase.
    slug = ascii_text.lower()

    # Step 3, replace non-alphanumeric characters with hyphens.
    slug = re.sub(r"[^a-z0-9]+", "-", slug)

    # Step 4, collapse consecutive hyphens.
    slug = re.sub(r"-+", "-", slug)

    # Step 5, trim leading and trailing hyphens.
    slug = slug.strip("-")

    # Step 6, fall back to a default if the input produced an
    # empty string (whitespace-only, punctuation-only, or non-
    # transliterable scripts).
    if not slug:
        slug = FALLBACK_SLUG

    # Step 7, truncate at a word boundary.
    if len(slug) > max_length:
        truncated = slug[:max_length]
        last_hyphen = truncated.rfind("-")
        if last_hyphen > 0:
            slug = truncated[:last_hyphen]
        else:
            slug = truncated

    # Step 8, reserved-word protection. Treat a reserved slug the
    # same way as a collision.
    base_slug = slug
    counter = 2
    if slug in RESERVED_SLUGS:
        suffix = f"-{counter}"
        slug = base_slug[: max_length - len(suffix)] + suffix
        counter += 1

    # Step 9, collision resolution against the supplied existence
    # check.
    if exists_fn is not None:
        while exists_fn(slug):
            suffix = f"-{counter}"
            slug = base_slug[: max_length - len(suffix)] + suffix
            counter += 1
            if counter > 10_000:
                raise ValueError(
                    f"Could not resolve slug collision for: {title}"
                )

    return slug