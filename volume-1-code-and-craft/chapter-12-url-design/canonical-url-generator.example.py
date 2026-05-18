#!/usr/bin/env python3
"""
canonical-url-generator.example.py

Reference implementation of the configurable canonical-URL generator
from Chapter 12 of SEO for Engineers, Volume 1. The CanonicalConfig
dataclass declares two parameter lists, and generate_canonical
classifies every incoming parameter against them:

    - In non_indexable_params: explicitly dropped. This list
      documents the parameters you know about and want stripped
      (tracking, pagination, sort order).
    - In indexable_params: included in the canonical (if truthy),
      sorted alphabetically.
    - In neither: logged as an unknown parameter so it surfaces in
      monitoring, then dropped. Treating unknowns as "drop and
      report" is safer than "include by default", which can leak
      session IDs or analytics parameters into canonical URLs as
      new tracking systems are added.

Both lists are active. Adding a parameter to non_indexable_params
explicitly drops it; adding to indexable_params explicitly
preserves it.

Usage:

    from canonical_url_generator import CanonicalConfig, generate_canonical

    config = CanonicalConfig(base_url="https://example.com")
    canonical = generate_canonical(
        path="/products",
        params={"category": "shoes", "utm_source": "email", "sort": "price"},
        config=config,
    )
    # -> "https://example.com/products?category=shoes"

Run this file directly to see the smoke-test output.

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


@dataclass
class CanonicalConfig:
    """Configuration for canonical URL generation."""

    # Parameters that change content and belong in the canonical URL.
    # Extend per-site or per-section as needed.
    indexable_params: set[str] = field(
        default_factory=lambda: {"category", "brand", "type"}
    )

    # Parameters known to change presentation rather than substance.
    # Explicitly dropped during canonicalization. Tracking,
    # pagination, sort, and view-preference parameters belong here.
    non_indexable_params: set[str] = field(
        default_factory=lambda: {
            "sort", "order", "page", "view", "display",
            "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "fbclid", "gclid",
            "msclkid", "mc_cid", "mc_eid", "ref", "sessionid", "sid",
        }
    )

    base_url: str = "https://example.com"


def generate_canonical(
    path: str,
    params: dict[str, str | list[str]],
    config: CanonicalConfig,
) -> str:
    """
    Generate the canonical URL for a given path and parameter set.

    Each incoming parameter is classified:
      - In non_indexable_params: dropped.
      - In indexable_params: included if truthy, sorted alphabetically.
      - In neither: logged and dropped.
    """
    canonical_params: dict[str, str | list[str]] = {}
    for k, v in sorted(params.items()):
        if k in config.non_indexable_params:
            continue
        if k in config.indexable_params:
            if v:
                canonical_params[k] = v
            continue
        # Unknown parameter. Log so the team can decide whether to
        # add it to one list or the other.
        logger.info(
            "canonical-url: unknown parameter %r dropped from "
            "canonical for path %s",
            k, path,
        )

    canonical = f"{config.base_url}{path}"
    if canonical_params:
        canonical += "?" + urlencode(canonical_params, doseq=True)
    return canonical


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    config = CanonicalConfig(base_url="https://example.com")

    cases = [
        # Plain page, no parameters.
        ("/products", {}),
        # Indexable parameter only.
        ("/products", {"category": "shoes"}),
        # Tracking parameter only, gets dropped.
        ("/products", {"utm_source": "email"}),
        # Mixed. category survives, sort and utm_* dropped.
        ("/products", {"category": "shoes", "sort": "price", "utm_source": "email"}),
        # Multi-value parameter.
        ("/products", {"category": ["shoes", "boots"]}),
        # Empty value is treated as absent.
        ("/products", {"category": "", "brand": "acme"}),
        # Unknown parameter triggers a log line.
        ("/products", {"category": "shoes", "promo": "summer25"}),
    ]

    for path, params in cases:
        result = generate_canonical(path, params, config)
        print(f"  {str(params):50s} -> {result}")
