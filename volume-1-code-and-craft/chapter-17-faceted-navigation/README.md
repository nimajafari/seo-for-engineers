# Chapter 17, Faceted Navigation

This directory contains the reference implementation, CI assertion
suite, and diagnostic instrumentation referenced in Chapter 17 of
*SEO for Engineers, Volume 1*. The artifacts here are the core of
the chapter's argument: the centralized tier classification function
that decides how Google should treat each faceted URL, the
parameter-order normalization decorator that prevents accidental
duplicate URLs, a CI test suite that asserts the head tags emitted
for each tier, a facet-specific `robots.txt` check, and the
BigQuery queries that verify in production whether the strategy is
working.

Five artifacts cover the chapter's full production stack. The
classifier, normalizer, and test suite are the production shipping
core. The `robots.txt` check and SQL queries are the diagnostic
instrumentation that complements them. Each piece maps to a specific
section of the chapter, so a reader can trace any artifact back to
the prose that motivates it.

## Scripts

### `facet_classifier.py`

The reference implementation of the `classify_request` function from
the chapter. Given a category slug and a query string, it returns
the indexing tier (Tier 1 indexable, Tier 2 canonicalized, or Tier 3
noindex) and the canonical URL where one applies. Tier 4 URLs are
blocked at the `robots.txt` layer and never reach this function;
Tier 5 state never produces a URL change.

The module exposes:

- `IndexingTier` enum, the four tiers used by the classification.
- `classify_request(category_slug, query_params)`, the main entry
  point. Returns a `Classification` dataclass with the tier, the
  canonical URL (when applicable), and the meta-robots directive
  string to emit.
- `register_indexable_combination(category_slug, facets)`, the API
  for adding an entry to the curated indexable set. Values are
  normalized (lowercased and stripped) at registration time so
  case-variant lookups resolve symmetrically. The reference
  implementation is in-memory for testability; in production it
  should be backed by a database or config store.
- `is_tracking_parameter(name)`, `is_transparent_parameter(name)`,
  the predicates that classify parameter names. Both ship with
  defaults that cover the common cases and are extensible.

The architecture is parameter-driven, not URL-pattern-driven. Every
new facet, sort variant, or tracking parameter is a one-line update
to one of three sets. There is no per-route logic; the same function
handles every category page on the site.

Usage from a Django, Flask, or FastAPI view:

```python
from facet_classifier import classify_request, IndexingTier

def category_view(request, category_slug):
    classification = classify_request(category_slug, dict(request.GET))

    if classification.tier == IndexingTier.CANONICALIZED:
        # Optionally 301-redirect to the canonical to save crawl
        # budget for pure tracking/transparent parameter URLs.
        # Don't redirect if the parameter has UX value
        # (e.g. ?sort= changes display).
        ...

    return render(request, "category.html", {
        "canonical_url": classification.canonical_url,
        "meta_robots": classification.meta_robots,
        "tier": classification.tier.name,
        # ... rest of context
    })
```

The template then emits the head tags based on the classification:

```html
{% if canonical_url %}
<link rel="canonical" href="{{ canonical_url }}">
{% endif %}
<meta name="robots" content="{{ meta_robots }}">
```

### `normalize_query.py`

The parameter-order normalization decorator from the chapter, plus
a framework-agnostic core function that can be wired into any web
stack. The chapter explains the rationale in detail; the short
version is that `?color=black&size=10` and `?size=10&color=black`
produce distinct URLs with identical content, which splits link
equity and floods the crawler with duplicates. Normalizing query
parameter order server-side, then 301-redirecting non-canonical
orderings, collapses the duplication at its source.

The module exposes:

- `canonicalize_query_string(query_string)`, the framework-agnostic
  core. Takes a raw query string, returns the canonical form
  (parameters in alphabetical order, values lowercased and trimmed,
  empty values stripped). Returns the same string if already
  canonical.
- `normalize_query_redirect`, a Django decorator that wraps a view.
  If the incoming URL's query string is not canonical, the decorator
  issues a 301 to the canonical form before the view runs.
- `flask_normalize_query`, a Flask `before_request` hook with the
  same semantics.
- `should_normalize(path)`, a predicate that controls whether
  normalization applies to a given path. By default it returns
  `True` for everything; override for paths where parameter order
  matters semantically (e.g., signed API endpoints).

The normalization is conservative. It lowercases values but not
keys, preserves multi-valued parameters in their original order
within a key, and skips paths flagged by `should_normalize`. The
default behavior is safe for category pages and most search-style
endpoints.

If Django or Flask is not installed, the corresponding adapter
raises a clear `RuntimeError` when called, so a missing dependency
produces an actionable error message rather than an opaque
`TypeError: 'NoneType' object is not callable`.

Usage with the Django decorator:

```python
from normalize_query import normalize_query_redirect

@normalize_query_redirect
def category_view(request, category_slug):
    # By the time this runs, the query string is guaranteed to be
    # in canonical form. Anything else has already been 301-ed.
    ...
```

Usage with Flask:

```python
from flask import Flask
from normalize_query import flask_normalize_query

app = Flask(__name__)
app.before_request(flask_normalize_query)
```

### `test_facet_head_tags.py`

The CI assertion suite from the chapter's Diagnostics section,
turned into a runnable test file. The suite asserts that the head
tags emitted on five canonical URL classes match the architecture
the chapter describes. It is designed to run against either the
local classifier (`facet_classifier.py`) or a live HTTP endpoint,
so the same suite serves as both a unit test and a smoke test.

Assertions include:

- The base category page returns `200`, emits `index, follow`, and
  has a self-canonical.
- A known-indexable single-facet URL (e.g., `?color=black` where
  black is in the curated set) returns `200`, emits `index, follow`,
  and has a self-canonical pointing at the same URL in normalized
  form.
- A known-non-indexable multi-facet URL returns `200`, emits
  `noindex, follow`, and either has no canonical tag or a
  self-canonical (never a cross-canonical to the base category).
- A URL with a known transparent parameter (`?sort=price_asc`)
  returns `200`, emits `index, follow`, and has a canonical pointing
  at the base category.
- A URL with a known blocked pattern (e.g., `?sessionid=abc123`)
  is disallowed in the active `robots.txt`.
- An empty-result facet URL returns `404` rather than `200` with an
  empty list.

The suite uses `pytest` and supports two run modes. The CLI options
`--base-url` and `--robots-url` are registered in `conftest.py`,
which pytest auto-loads.

Usage.

Run against the local classifier
```
pytest test_facet_head_tags.py
```

Run against a live HTTP endpoint
```
pytest test_facet_head_tags.py --base-url https://staging.example.com
```

Run against production for post-deploy verification
```
pytest test_facet_head_tags.py \
  --base-url https://www.example.com \
  --robots-url https://www.example.com/robots.txt
```

The HTTP mode fetches each URL, parses the response, extracts the
canonical tag and the `meta name="robots"` content (or the
`X-Robots-Tag` header), and asserts against the expected values. It
catches both pre-deploy regressions (the local classifier mode) and
post-deploy serving issues (the HTTP mode), which the chapter
argues are different failure surfaces requiring separate coverage.

Install.
```
pip install -r requirements.txt
```

### `check_robots_facets.py`

The faceted-navigation-specific `robots.txt` CI check from Chapter
17's *Strategy 1* section. Asserts a list of business-critical
category and product URLs remain crawlable by Googlebot, and that
the standard Tier 4 patterns (session IDs, tracking parameters,
infinite-combination parameters, internal search) remain blocked.

This is the minimum defensive check for any deploy that touches
`robots.txt` on a site with faceted navigation. For broader
`robots.txt` validation (catch-all-`Disallow` detection,
asset-path blocking, assertion-suite formats, post-deploy live
verification) see the Chapter 15 tooling at
[`chapter-15-robots-txt/`](../chapter-15-robots-txt/), which is the
more general implementation.

Usage.
```
python check_robots_facets.py https://www.example.com/robots.txt
```

Edit the `CRITICAL_URLS` and `BLOCKED_URLS` lists at the top of the
file to match your site's URL patterns before deploying.

### `facet_log_analysis.sql`

The BigQuery analysis queries from the chapter's *Measuring the
Impact* section. Four queries, in order of how often they should
run.

1. **Monthly URL-class distribution.** The diagnostic the chapter
   builds toward. Tells you what percentage of Googlebot's crawl
   went to URLs you classify as wasted versus clean canonical URLs.
2. **Weekly trend of clean vs wasted crawl.** The same
   classification over time. Use this to detect regressions after
   a deploy.
3. **Top wasted URL patterns.** When Query 1 shows a high
   `multi_facet` share, Query 3 names the specific paths
   responsible. This is the prioritized cleanup worklist.
4. **Response-code distribution for facet URLs.** Verifies the
   chapter's empty-result-facet-must-return-404 assertion. Facet
   URLs returning `200` with low content size are soft-`404`
   candidates.

The queries assume a BigQuery `access_logs` table with
`request_uri`, `user_agent`, `request_date`, and `status_code`
columns. Adjust column names to match your schema. The regex
patterns translate to any SQL dialect with a `regexp_contains`
equivalent (PostgreSQL `~`, MySQL `REGEXP`, Snowflake `REGEXP_LIKE`).

For verified-Googlebot-only analysis, pre-filter the logs using
Chapter 16's
[`verify-googlebot.py`](../chapter-16-crawl-budget/verify-googlebot.py)
before loading into BigQuery. The chapter's `user_agent LIKE`
filter accepts spoofed user-agents and is therefore an upper bound
on real Googlebot traffic.

## Wiring into CI

The recommended pipeline shape is two gates.

**Pre-deploy (blocking):**

```yaml
- name: Run faceted navigation unit tests
  run: |
    cd volume-1-code-and-craft/chapter-17-faceted-navigation
    pip install -r requirements.txt
    pytest test_facet_head_tags.py

- name: Validate robots.txt facet patterns
  run: |
    cd volume-1-code-and-craft/chapter-17-faceted-navigation
    python check_robots_facets.py https://www.example.com/robots.txt
```

The pytest step runs the classifier against the curated set of
indexable combinations and the known-blocked patterns, asserting
that the in-memory facet registry produces the expected tier for
each input. The `robots.txt` step asserts that the facet-specific
crawlable and blocked URL lists hold against the live file.
Failures in either are caught before merge.

**Post-deploy (blocking):**

```yaml
- name: Verify faceted head tags on production
  run: |
    cd volume-1-code-and-craft/chapter-17-faceted-navigation
    pytest test_facet_head_tags.py \
      --base-url https://www.example.com \
      --robots-url https://www.example.com/robots.txt
```

This runs the same suite against the live origin, catching
CDN-layer rewrites, edge worker misbehavior, head-tag injection
order bugs, and any other failure mode that exists between the
classifier's output and what Googlebot actually sees.

**Weekly diagnostic (informational):**

Run the SQL queries on a schedule against your access log dataset.
Track the `multi_facet` and `single_facet` shares from Query 1
week-over-week. A rising trend is the leading indicator of facet
strategy drift and the trigger for a registry review.

Combined, the three layers implement the discipline the Manager
Lens section argues for: every change that touches the facet
registry or URL handling passes through assertions that match the
architecture on both sides of the deploy boundary, and ongoing log
analysis catches drift between deploys.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.
