# Chapter 12, URL Design as an Engineering Discipline

This directory contains the diagnostic and test scripts referenced
in Chapter 12 of *SEO for Engineers, Volume 1*. The scripts cover
the two URL-design checks that engineering teams most often need
beyond standard crawler output. Validating a population of URLs
against the convention rules the chapter establishes, and
exercising a slug-generation implementation against the edge cases
that bite in production.

## Scripts

### `url-design-linter.py`

A Python script that takes a sitemap URL (or a list of URLs from a
file) and validates each URL against the URL design rules Chapter
12 establishes as engineering standards.

The script runs the following checks against every URL.

- **Case enforcement.** Every URL path must be lowercase. Mixed-case
  paths are flagged as creating duplicate-content risk.
- **Trailing slash consistency.** The trailing slash convention is
  configurable (require, forbid, or skip). Once configured, every
  URL must match the convention.
- **Insignificant query parameters.** URLs in canonical positions
  (sitemap, internal links) must not contain tracking, session, or
  display parameters. The default list matches the
  `INSIGNIFICANT_PARAMS` set from the chapter.
- **Reserved slugs in path segments.** Path segments matching
  reserved keywords (admin, api, login, etc.) are flagged as likely
  routing collisions.
- **URL length.** URLs exceeding a configurable maximum length are
  flagged for review. The default threshold is 2048 characters,
  matching the URL length most crawlers and CDNs handle without
  issue.
- **Encoded character density.** URLs with a high percentage of
  percent-encoded characters are flagged, since these often
  indicate the slug-generation step is incorrectly preserving
  characters that should have been transliterated or stripped.
- **Deep nesting.** URLs with more than a configurable number of
  path segments are flagged as fragile, since deep hierarchies
  break on taxonomy changes.

Usage:
Lint URLs from a sitemap
python url-design-linter.py --sitemap https://example.com/sitemap.xml
Lint URLs from a file (one per line)
python url-design-linter.py --urls urls.txt
Require trailing slashes (default is to forbid them)
python url-design-linter.py --sitemap <url> --trailing-slash require
Customize the length and depth thresholds
python url-design-linter.py --sitemap <url> --max-length 1024 --max-depth 6
Write a JSON report
python url-design-linter.py --sitemap <url> --output report.json

The script exits non-zero if any high-severity issue is found, so
it can be wired into CI as a deployment gate on sitemap changes or
on the URL output of a build pipeline.

Install:
pip install -r requirements.txt

### `slug-generator-test-suite.py`

A Python test suite that exercises a slug-generation function
against the battery of edge cases Chapter 12 identifies as failure
points in production. The script imports a `generate_slug` function
from a module of your choice (configurable on the command line) and
runs each test case against it, reporting which cases pass and
which fail.

The test cases cover the following.

- **Basic input.** Lowercase, hyphen-separation, alphanumeric
  preservation.
- **Diacritic stripping.** Latin-script characters with diacritics
  (Zürich, café, naïve, São Paulo) must produce ASCII output.
- **CJK and Cyrillic handling.** Non-Latin scripts must either
  transliterate to ASCII (if the implementation supports it) or
  produce a non-empty slug via fallback (timestamp or hash). An
  empty slug from non-Latin input is a fail.
- **Reserved word protection.** Titles that would produce reserved
  slugs (admin, api, login, etc.) must be disambiguated, not
  returned as-is.
- **Length truncation.** Long titles must truncate at a word
  boundary, not mid-word. The output must respect the configured
  max length.
- **Collision resolution.** Repeated generation against a tracked
  set of existing slugs must produce unique outputs (`slug`,
  `slug-2`, `slug-3`, ...).
- **Race-condition simulation.** Two concurrent attempts to create
  the same slug against a SQLite database with a unique constraint
  must result in exactly one success and one disambiguated slug,
  with no IntegrityError surfacing to the caller.
- **Empty and whitespace input.** Empty strings, whitespace-only
  strings, and strings of only punctuation must produce a defined
  fallback slug, not an empty string or an exception.
- **Maximum-length edge cases.** A title that produces exactly the
  max length must be accepted. A title one character over must
  truncate cleanly.

The script is structured so that you can point it at any
`generate_slug` implementation in your codebase and get a pass/fail
report. This makes it usable as both a regression test for an
existing implementation and a conformance test when migrating
between implementations.

Usage:
Test the example implementation included in this directory
python slug-generator-test-suite.py --module example_slug_implementation --function generate_slug
Test your own implementation
python slug-generator-test-suite.py --module myapp.slugs --function make_slug
Run only specific test categories
python slug-generator-test-suite.py --module example_slug_implementation --function generate_slug --only diacritics,collisions,length

The script exits non-zero if any test case fails.

Install:
pip install -r requirements.txt

## Reference snippets

Five lift-and-paste files that pair with the slug generator and
URL design linter:

### `generate-slug.example.ts`

TypeScript port of `example_slug_implementation.py` for Node.js
backends. Matches the Python API function-for-function:
NFKD + diacritic stripping, lowercase, hyphen-collapse, trim,
word-boundary truncation, `FALLBACK_SLUG` for empty input,
reserved-word protection, and async `existsFn`-based collision
resolution. Reserved-word and collision steps share a counter so
a slug that hits both keeps incrementing rather than restarting.

### `canonical-url-generator.example.py`

The `CanonicalConfig` dataclass and `generate_canonical` function
from chapter 12. Each parameter is classified against two lists:
`non_indexable_params` (explicit drop), `indexable_params`
(explicit include, sorted), and parameters in neither list are
logged and dropped — so unknown tracking parameters surface in
monitoring rather than leaking into canonical URLs.

Run directly to see a smoke test:

```bash
python canonical-url-generator.example.py
```

### `url-normalization.example.py`

Two independent utilities. `normalize_url(url)` lowercases scheme
and host, sorts query parameters alphabetically (including
multi-values), strips trailing slashes from non-root paths, and
strips the fragment. `strip_insignificant_params(url)` removes
tracking, session, and analytics parameters via the
`INSIGNIFICANT_PARAMS` frozenset. Use these when generating
canonical URLs, sitemap entries, or internal links.

Run directly for a smoke test:

```bash
python url-normalization.example.py
```

### `article-router.example.py`

Flask route handler for the `/articles/{id}/{slug}` pattern. The
numeric ID is the true routing key; the slug is cosmetic. A
request with the wrong slug 301-redirects to the canonical slug,
so the system tolerates slug changes without breaking external
links. Includes the optional handler for the slug-less form
(`/articles/12345`) that canonicalizes to the full URL.

The `Article` class is stubbed in-memory so the file runs without
a database — replace it with your ORM.

### `trailing-slash-middleware.example.js`

Express middleware that 301-redirects any non-root path ending in
`/` to the same URL without the trailing slash, preserving query
strings. Apply early in the pipeline, before routing. Single layer
of enforcement (Express app OR CDN, never both — chapter 12's
failure mode 3).

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.