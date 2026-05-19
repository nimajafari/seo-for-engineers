"""
facet_classifier.py

Reference implementation of the centralized tier classification
function from Chapter 17 of SEO for Engineers, Volume 1.

A category page request maps to one of three tiers. The function is
the single point of decision for how every faceted URL on the site
should be treated by Google.

  Tier 1 (INDEXABLE):    self-canonical, index, follow, in sitemap
  Tier 2 (CANONICALIZED): canonical to base, index, follow
  Tier 3 (NOINDEX):       no canonical or self-canonical, noindex, follow

Tier 4 (robots.txt-blocked) URLs do not reach this function.
Tier 5 (pure client state) never produces a URL change.

The facet registry is in-memory for testability. In production it
should be backed by a config store or database that the sitemap
generator also reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlencode

BASE_HOST = "https://www.example.com"


class IndexingTier(Enum):
    INDEXABLE = 1
    CANONICALIZED = 2
    NOINDEX = 3
    BLOCKED = 4  # handled by robots.txt; included for completeness


@dataclass(frozen=True)
class Classification:
    tier: IndexingTier
    canonical_url: str | None
    meta_robots: str


# Parameters that are tracking-only. They never affect content and
# their canonical is always the URL without them.
DEFAULT_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "gbraid", "wbraid", "dclid",
    "fbclid",
    "msclkid",
    "mc_cid", "mc_eid",
    "sessionid", "sid", "PHPSESSID", "jsessionid",
    "_ga", "_gl",
})

# Parameters that change presentation but not the set of indexable
# results. Their canonical is the base category page.
DEFAULT_TRANSPARENT_PARAMS = frozenset({
    "sort", "order",
    "per_page", "page_size", "items_per_page",
    "view", "display",
})


# In-memory facet registry. Maps category slug to a set of frozensets
# of (param_name, param_value) tuples that have been promoted to
# Tier 1.
_INDEXABLE_COMBINATIONS: dict[str, set[frozenset]] = {}


def register_indexable_combination(category_slug: str, facets: dict) -> None:
    """Add a facet combination to the curated indexable set.

    Facet values are normalized at registration time using the same
    rules classify_request applies at lookup time (lowercased and
    stripped), so case-variant registrations resolve symmetrically.

    Example:
        register_indexable_combination("shoes", {"color": "black"})
        register_indexable_combination("shoes", {"brand": "nike"})
    """
    normalized = {
        key: _normalize_facet_value(value) for key, value in facets.items()
    }
    signature = frozenset(normalized.items())
    _INDEXABLE_COMBINATIONS.setdefault(category_slug, set()).add(signature)


def get_indexable_combinations(category_slug: str) -> set[frozenset]:
    return _INDEXABLE_COMBINATIONS.get(category_slug, set())


def is_tracking_parameter(name: str,
                          extra: set | None = None) -> bool:
    return name in DEFAULT_TRACKING_PARAMS or (extra is not None and name in extra)


def is_transparent_parameter(name: str,
                             extra: set | None = None) -> bool:
    return name in DEFAULT_TRANSPARENT_PARAMS or (extra is not None and name in extra)


def _normalize_facet_value(value: str) -> str:
    """Lowercase and strip a facet value for canonical comparison."""
    return value.lower().strip()


def classify_request(
    category_slug: str,
    query_params: dict,
    extra_tracking: set | None = None,
    extra_transparent: set | None = None,
) -> Classification:
    """Classify a request into an indexing tier.

    Args:
        category_slug: The category path segment, without leading slash.
        query_params: Flat dict of query parameter name to value.
        extra_tracking: Optional additional tracking parameter names.
        extra_transparent: Optional additional transparent parameter names.

    Returns:
        Classification with tier, canonical URL (where applicable),
        and meta-robots directive.
    """
    base_url = f"{BASE_HOST}/category/{category_slug}"

    tracking = {
        k: v for k, v in query_params.items()
        if is_tracking_parameter(k, extra_tracking)
    }
    transparent = {
        k: v for k, v in query_params.items()
        if is_transparent_parameter(k, extra_transparent)
    }
    facet_params = {
        k: v for k, v in query_params.items()
        if k not in tracking and k not in transparent
    }

    # Q1: Only tracking parameters? Canonical is the base URL.
    if tracking and not facet_params and not transparent:
        return Classification(
            tier=IndexingTier.CANONICALIZED,
            canonical_url=base_url,
            meta_robots="index, follow",
        )

    # Q2: Only transparent parameters (or transparent plus tracking)? Same.
    if transparent and not facet_params:
        return Classification(
            tier=IndexingTier.CANONICALIZED,
            canonical_url=base_url,
            meta_robots="index, follow",
        )

    # Q3: No facet parameters at all? Base category, indexable.
    if not facet_params:
        return Classification(
            tier=IndexingTier.INDEXABLE,
            canonical_url=base_url,
            meta_robots="index, follow",
        )

    # Q4: Facet parameters present. Check the curated indexable set.
    normalized_facets = {
        k: _normalize_facet_value(v) for k, v in facet_params.items()
    }
    facet_signature = frozenset(normalized_facets.items())

    if facet_signature in get_indexable_combinations(category_slug):
        sorted_params = sorted(normalized_facets.items())
        canonical = f"{base_url}?{urlencode(sorted_params)}"
        return Classification(
            tier=IndexingTier.INDEXABLE,
            canonical_url=canonical,
            meta_robots="index, follow",
        )

    # Default: facet combination is not in the curated set.
    # Tier 3: noindex, no canonical to a different URL.
    return Classification(
        tier=IndexingTier.NOINDEX,
        canonical_url=None,
        meta_robots="noindex, follow",
    )