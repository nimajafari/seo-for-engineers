"""
test_facet_head_tags.py

CI assertion suite for faceted navigation head tags. Runs in two
modes:

  1. Local (default): asserts against the in-memory classifier in
     facet_classifier.py.
  2. HTTP: asserts against a live origin. Pass --base-url and
     optionally --robots-url to enable.

Both modes test the same architectural contract:

  - Tier 1 URLs: 200, index/follow, self-canonical.
  - Tier 2 URLs: 200, index/follow, canonical to base.
  - Tier 3 URLs: 200, noindex/follow, self-canonical or no canonical.
  - Tier 4 URLs: disallowed in robots.txt.
  - Empty-result facets: 404 (not 200 with empty results).
"""

from __future__ import annotations

import urllib.robotparser

import pytest

from facet_classifier import (
    IndexingTier,
    classify_request,
    register_indexable_combination,
)


# --- Test fixtures: the facet registry under test ----------------

def setup_module(module):
    """Register the curated Tier 1 combinations for the test catalog."""
    register_indexable_combination("shoes", {"color": "black"})
    register_indexable_combination("shoes", {"color": "white"})
    register_indexable_combination("shoes", {"brand": "nike"})
    register_indexable_combination("shoes", {"category": "running"})


# --- Local-mode tests (classifier semantics) --------------------
# CLI options (--base-url, --robots-url) and the matching session
# fixtures live in conftest.py, which is where pytest expects them.

class TestClassifierLocal:
    """Assert the classifier's output for each tier."""

    def test_base_category_is_indexable(self):
        c = classify_request("shoes", {})
        assert c.tier == IndexingTier.INDEXABLE
        assert c.meta_robots == "index, follow"
        assert c.canonical_url and c.canonical_url.endswith("/category/shoes")

    def test_curated_facet_is_indexable(self):
        c = classify_request("shoes", {"color": "black"})
        assert c.tier == IndexingTier.INDEXABLE
        assert c.meta_robots == "index, follow"
        assert c.canonical_url is not None
        assert "color=black" in c.canonical_url

    def test_uncurated_facet_is_noindex(self):
        c = classify_request("shoes", {"color": "neon-green"})
        assert c.tier == IndexingTier.NOINDEX
        assert c.meta_robots == "noindex, follow"
        assert c.canonical_url is None  # no cross-canonical on noindex

    def test_multi_facet_outside_registry_is_noindex(self):
        c = classify_request("shoes", {"color": "black", "size": "10"})
        assert c.tier == IndexingTier.NOINDEX
        assert c.meta_robots == "noindex, follow"
        assert c.canonical_url is None

    def test_tracking_only_canonicalizes_to_base(self):
        c = classify_request("shoes", {"utm_source": "newsletter"})
        assert c.tier == IndexingTier.CANONICALIZED
        assert c.meta_robots == "index, follow"
        assert c.canonical_url.endswith("/category/shoes")

    def test_transparent_only_canonicalizes_to_base(self):
        c = classify_request("shoes", {"sort": "price_asc"})
        assert c.tier == IndexingTier.CANONICALIZED
        assert c.meta_robots == "index, follow"
        assert c.canonical_url.endswith("/category/shoes")

    def test_session_parameter_canonicalizes_to_base(self):
        c = classify_request("shoes", {"sessionid": "abc123"})
        assert c.tier == IndexingTier.CANONICALIZED
        assert c.canonical_url.endswith("/category/shoes")

    def test_facet_value_is_case_insensitive(self):
        c1 = classify_request("shoes", {"color": "black"})
        c2 = classify_request("shoes", {"color": "BLACK"})
        c3 = classify_request("shoes", {"color": "Black"})
        assert c1.tier == c2.tier == c3.tier == IndexingTier.INDEXABLE

    def test_registration_normalizes_value_case(self):
        """
        Regression: registering a value with non-lowercase casing
        (e.g. "Red") must still match a lowercase lookup. Before the
        fix, registration stored the raw value and the lookup
        normalized only the input, so case-mismatched pairs silently
        fell through to NOINDEX.
        """
        register_indexable_combination("shoes", {"color": "Red"})
        assert classify_request(
            "shoes", {"color": "red"}
        ).tier == IndexingTier.INDEXABLE
        assert classify_request(
            "shoes", {"color": "RED"}
        ).tier == IndexingTier.INDEXABLE


# --- HTTP-mode tests (live origin) ------------------------------

@pytest.fixture
def http_client(base_url):
    if base_url is None:
        pytest.skip("--base-url not provided; skipping HTTP-mode tests")
    import requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": "FacetHeadTagTester/1.0 (+chapter-17-tooling)",
    })
    return session


def _extract_head_tags(html: str) -> dict:
    """Return canonical_url and meta_robots from an HTML response."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    canonical = None
    canonical_link = soup.find("link", rel="canonical")
    if canonical_link and canonical_link.get("href"):
        canonical = canonical_link["href"].strip()

    meta_robots = None
    meta_tag = soup.find("meta", attrs={"name": "robots"})
    if meta_tag and meta_tag.get("content"):
        meta_robots = meta_tag["content"].strip().lower()

    return {"canonical": canonical, "meta_robots": meta_robots}


def _x_robots_tag(response) -> str | None:
    header = response.headers.get("X-Robots-Tag")
    return header.strip().lower() if header else None


class TestHeadTagsHTTP:
    """Assert the live origin emits the head tags the classifier specifies."""

    def test_base_category_serves_index_and_self_canonical(self, http_client, base_url):
        url = f"{base_url.rstrip('/')}/category/shoes"
        resp = http_client.get(url, allow_redirects=False)
        assert resp.status_code == 200, f"expected 200, got {resp.status_code}"

        tags = _extract_head_tags(resp.text)
        x_robots = _x_robots_tag(resp)
        robots_directive = tags["meta_robots"] or x_robots or ""

        assert "noindex" not in robots_directive, \
            f"base category {url} should be indexable; saw '{robots_directive}'"
        assert tags["canonical"] is not None, "base category must have a canonical tag"
        assert tags["canonical"].rstrip("/") == url.rstrip("/"), \
            "base category should have a self-canonical"

    def test_uncurated_facet_serves_noindex(self, http_client, base_url):
        url = f"{base_url.rstrip('/')}/category/shoes?color=neon-green"
        resp = http_client.get(url, allow_redirects=False)
        assert resp.status_code == 200

        tags = _extract_head_tags(resp.text)
        x_robots = _x_robots_tag(resp)
        robots_directive = tags["meta_robots"] or x_robots or ""

        assert "noindex" in robots_directive, \
            f"uncurated facet {url} must emit noindex; saw '{robots_directive}'"

    def test_noindex_facet_has_no_cross_canonical(self, http_client, base_url):
        url = f"{base_url.rstrip('/')}/category/shoes?color=neon-green"
        resp = http_client.get(url, allow_redirects=False)
        tags = _extract_head_tags(resp.text)

        if tags["canonical"]:
            assert tags["canonical"].rstrip("/") == url.rstrip("/").split("?")[0] + "?color=neon-green", \
                f"noindex page must use self-canonical or no canonical, " \
                f"never a cross-canonical to a different URL; got {tags['canonical']}"

    def test_tracking_url_canonicalizes_to_base(self, http_client, base_url):
        url = f"{base_url.rstrip('/')}/category/shoes?utm_source=newsletter"
        base_category = f"{base_url.rstrip('/')}/category/shoes"
        resp = http_client.get(url, allow_redirects=False)

        # Either the origin 301s to base, or it serves 200 with a canonical
        # to base. Both are acceptable; the chapter argues for either.
        if resp.status_code in (301, 308):
            location = resp.headers["Location"].split("?")[0]
            assert location.rstrip("/") == base_category.rstrip("/")
        else:
            assert resp.status_code == 200
            tags = _extract_head_tags(resp.text)
            assert tags["canonical"] is not None
            assert tags["canonical"].rstrip("/") == base_category.rstrip("/"), \
                f"tracking URL must canonicalize to base; got {tags['canonical']}"


class TestRobotsTxt:
    """Assert blocked patterns are actually disallowed in production."""

    def test_session_pattern_is_blocked(self, http_client, robots_url, base_url):
        if robots_url is None:
            pytest.skip("--robots-url not provided")

        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()

        blocked_url = f"{base_url.rstrip('/')}/category/shoes?sessionid=abc123"
        assert not rp.can_fetch("Googlebot", blocked_url), \
            f"session URL {blocked_url} must be disallowed in robots.txt"

    def test_internal_search_is_blocked(self, http_client, robots_url, base_url):
        if robots_url is None:
            pytest.skip("--robots-url not provided")

        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        rp.read()

        search_url = f"{base_url.rstrip('/')}/search?q=anything"
        assert not rp.can_fetch("Googlebot", search_url), \
            f"internal search {search_url} should be disallowed in robots.txt"


class TestEmptyResultFacets:
    """Empty-result facets must 404, not serve 200 with an empty list."""

    def test_impossible_combination_returns_404(self, http_client, base_url):
        # A facet combination that should yield zero products.
        url = f"{base_url.rstrip('/')}/category/shoes?color=neon-green&size=99"
        resp = http_client.get(url, allow_redirects=False)
        assert resp.status_code == 404, \
            f"empty-result facet {url} must return 404, not {resp.status_code}"