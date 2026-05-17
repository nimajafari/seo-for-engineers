# Chapter 11, Internationalization and Multilingual SEO Engineering

This directory contains the diagnostic scripts referenced in Chapter
11 of *SEO for Engineers, Volume 1*. The scripts cover the two
internationalization checks engineers most often need beyond what
standard crawlers detect. Validating that an hreflang cluster is a
complete bidirectional graph with correct codes and reachable URLs,
and verifying that locale URLs serve their content directly without
locale-adaptive substitution based on request headers.

## Scripts

### `hreflang-validator.py`

A Python script that parses sitemap XML (with sitemap-index support)
and validates the hreflang annotations against the five rules
Chapter 11 identifies as non-negotiable. The script can also fetch
each declared hreflang URL to verify that it returns HTTP 200 and is
not a redirect target.

The script runs five validation passes.

- **Bidirectional confirmation.** Every declaration A → B must have
  a corresponding declaration B → A.
- **Self-reference.** Every URL must include a hreflang annotation
  pointing to itself.
- **ISO 639-1 and ISO 3166-1 Alpha-2 code format.** Every hreflang
  value must match `x-default` or a 2-letter language code with an
  optional 2-letter region code.
- **x-default presence.** A cluster should include an `x-default`
  annotation. This is recommended rather than required, so it is
  flagged as a warning rather than an error by default.
- **Live URL verification (optional).** When `--check-urls` is
  passed, the script fetches every declared URL and flags
  annotations that point to redirects, 404s, or other non-200
  responses.

The script accepts either a local sitemap file path or a remote
sitemap URL. Sitemap indexes are followed recursively up to a
configurable depth.

Usage:
Validate a local sitemap file
python hreflang-validator.py --sitemap sitemap.xml
Fetch and validate a remote sitemap
python hreflang-validator.py --sitemap https://example.com/sitemap.xml
Include live URL verification
python hreflang-validator.py --sitemap https://example.com/sitemap.xml --check-urls
Treat x-default as required (errors instead of warnings)
python hreflang-validator.py --sitemap https://example.com/sitemap.xml --require-x-default
Write a JSON report
python hreflang-validator.py --sitemap https://example.com/sitemap.xml --output report.json

The script exits non-zero if any high-severity issue is found, so it
can be wired into CI as a deployment gate on sitemap changes.

Install:
pip install -r requirements.txt

### `locale-routing-checker.js`

A Playwright-based script that verifies the rule Chapter 11
establishes as the foundation of multilingual SEO. Locale URLs must
serve their content directly with a 200 status, must not redirect,
and must not be locale-adaptive based on the `Accept-Language` header
or IP geolocation.

For each locale URL the script verifies the following.

- The page returns HTTP 200 without any redirects, regardless of
  the `Accept-Language` header sent by the client.
- The page returns the same 200 response for at least three
  different `Accept-Language` headers (a control header, a
  conflicting locale header, and a matching locale header), proving
  the response is not header-adaptive.
- The rendered DOM's `<html lang>` attribute matches the locale
  declared in the URL path.
- The page's `<link rel="canonical">` is self-referencing (canonical
  equals the request URL), not pointing to another locale.
- The page has at least one hreflang annotation declaring its own
  URL (self-referencing hreflang).

The script accepts a list of locale URLs to check. For sites with
many locales, the URL list is typically generated from the sitemap
or from a build-time list of supported locales.

Usage:
Check a single locale URL
node locale-routing-checker.js --url https://example.com/de/produkt --locale de
Check multiple URLs from a JSON file
node locale-routing-checker.js --urls urls.json

Where `urls.json` is:

```json
[
  { "url": "https://example.com/en/product", "locale": "en" },
  { "url": "https://example.com/de/produkt", "locale": "de" },
  { "url": "https://example.com/fr/produit", "locale": "fr" }
]
```

The script exits non-zero if any high-severity issue is found.

Install:

```bash
npm install
npx playwright install chromium
```

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.