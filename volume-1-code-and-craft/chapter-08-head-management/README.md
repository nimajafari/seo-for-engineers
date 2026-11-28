# Chapter 8, Meta Tags, Canonical Tags, and Head Management

This directory contains the diagnostic scripts referenced in Chapter 8
of *SEO for Engineers, Volume 1*. The scripts audit the contents of
the `<head>` element across a site and provide a CI gate against the
most expensive head-management failure mode: accidental `noindex`
deployments to production.

## Setup

This chapter has two toolchains, Python and Node.js (20 or later). From
this directory:

Python:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Node.js:

```bash
npm install
npx playwright install chromium
```

## Tests

The tests run offline. The Python tests serve pages from a local HTTP
server, and they also cover `canonical-status-check.sh`, which needs
`bash`, `curl`, and `perl`. The Node tests cover the pure parts of the
scripts and need no `npm install`, because Playwright is only loaded
when a script actually runs.

```bash
python -m pytest -q    # head-audit.py, canonical-status-check.sh, gsc-index-coverage.py
npm test               # noindex-deployment-gate.js, generate-title.example.js
```

From the repository root, `make test CHAPTER=chapter-08-head-management`
runs the Python suite, and `make test-js-chapter-08-head-management`
runs the Node suite.

## Scripts

### `head-audit.py`

A Python audit that fetches a URL (or a list of URLs from a sitemap)
and inspects every page's `<head>` against the checklist from
Chapter 8.

For each page, the audit reports findings in three severity buckets.

**High severity.** Missing `<title>`, empty `<title>`, multiple
`<title>` elements, missing `<link rel="canonical">` (or one with no
`href`), multiple canonical tags, canonical URL that does not answer
200 itself, including one that redirects (when
`--check-canonical-status` is set), `noindex` directive on a URL the
caller flagged as indexable, and the `noindex` plus
canonical-to-an-indexable-URL conflict from Failure Mode 5.

**Medium severity.** Relative canonical URL, canonical host that does
not match the page host, generic title values (`Untitled`, `Home`, or
the `og:site_name` alone), and a missing or duplicated
`<meta name="description">`.

**Low severity.** Missing `og:title`, missing `og:image`, missing
`og:url`, missing X (Twitter) card markup, viewport meta tag missing or
blocking zoom, and a missing or non-UTF-8 charset declaration.

How the page is read:

- Title, canonical, and the other metadata come from `<head>` only. An
  SVG `<title>` in the body is not a second title, and a
  `<link rel="canonical">` in the body is ignored, as Google ignores it.
- Robots meta tags are read from the whole document, every
  `robots` and `googlebot` tag counts, and the name is matched
  case-insensitively. Every `X-Robots-Tag` header counts too.
- Directives are parsed, not substring-matched. `noindex` and `none`
  are noindex; `max-image-preview:none` is not. A `googlebot:` prefix
  in `X-Robots-Tag` is understood.
- Redirects are followed and the final URL is audited, so a noindex
  page reached through a redirect, or one with a relative
  self-canonical, is not reported as a Failure Mode 5 conflict.
- A page that answers HTTP 400 or above is reported as an error, not
  audited.

The script reads URLs from one of three sources: a single URL via
`--url`, a newline-separated list via `--urls-file`, or a sitemap or
sitemap index via `--sitemap`. `--limit N` audits only the first N
URLs.

Usage:

```bash
# Audit a single URL
python head-audit.py --url https://example.com/

# Audit a list of URLs
python head-audit.py --urls-file urls.txt

# Audit the first 50 pages from a sitemap
python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50

# Also verify that each canonical URL returns HTTP 200 without redirecting
python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50 --check-canonical-status

# A URL that is meant to be noindex
python head-audit.py --url https://example.com/account --expect-noindex

# JSON output to a file
python head-audit.py --url https://example.com/ --output report.json
```

In a `--urls-file`, append `noindex` to a line to mark that URL as
intentionally non-indexable:

```text
https://example.com/
https://example.com/account/settings    noindex
```

Exit codes: 0 no high-severity findings, 1 at least one high-severity
finding, 2 usage error or a URL that could not be audited (network
error or HTTP status >= 400) and no high-severity findings elsewhere.

### `noindex-deployment-gate.js`

A Playwright-based CI gate designed to run before a production
deployment. It fetches a list of URLs that are supposed to be
indexable (typically the staging build of a release candidate) and
asserts the absence of `noindex` directives in both the meta robots
tag and the `X-Robots-Tag` response header.

Failure Mode 4 in the chapter, accidental `noindex` deployed to
production, is the most expensive head-management failure. This
script is intended to be the blocking gate that prevents it.

The script runs two checks on every URL.

First, an HTTP-level check. The URL is fetched, following redirects.
An HTTP error status blocks the URL, because a page that answers 404
or 500 is not indexable either. Every `X-Robots-Tag` header is parsed,
and a `noindex` or `none` directive blocks the URL.

Second, a rendered-DOM check. The page is loaded in headless Chromium.
After the load event the gate waits for the network to go quiet
(capped at 5 seconds) plus `--settle-ms` (default 500), then reads
every `<meta name="robots">` and `<meta name="googlebot">` tag, with
the name matched case-insensitively. This catches `noindex` injected
by client-side JavaScript after initial render, which the HTTP check
would miss. Raise `--settle-ms` if your app injects head tags late.

Directives are parsed with the same rules as `head-audit.py`:
`max-image-preview:none` does not block, `googlebot: noindex` does.

Usage:

```bash
node noindex-deployment-gate.js --urls https://staging.example.com/ https://staging.example.com/products/sample

# From a newline-separated file
node noindex-deployment-gate.js --urls-file staging-urls.txt

# Wait longer for late client-side head changes
node noindex-deployment-gate.js --settle-ms 2000 --urls-file staging-urls.txt
```

Exit codes: 0 every URL passed, 1 at least one URL carries `noindex`,
2 usage error or a URL that could not be checked (fetch or page load
failed, or HTTP status >= 400) and no `noindex` elsewhere. Treat any
non-zero exit as a failed required check.

### `canonical-status-check.sh`

A small Bash script that reads a list of URLs and verifies each
URL's `<link rel="canonical">` tag points at a URL returning HTTP
200. Catches canonical drift, where a canonical continues pointing
at a URL that has since been redirected, removed, or otherwise
stopped returning 200. Designed to run in CI as a regression gate.

The page itself is fetched following redirects, and a page that
returns an HTTP error fails. The canonical URL is requested without
following redirects: it has to answer 200 itself, because a canonical
that redirects to a 200 is the drift this gate exists to catch.
Relative canonicals, canonicals with no `href`, and pages with more
than one canonical also fail.

Usage:

```bash
./canonical-status-check.sh urls.txt
```

`urls.txt` should contain one URL per line; blank lines and lines
starting with `#` are skipped. Exits 1 if any canonical issue is
found, 2 on a usage error (missing, unreadable, or empty file), and 0
otherwise.

Portability. The canonical is extracted by a Perl one-liner (Perl
ships with macOS and the usual Linux CI images), so the same file
runs on Linux CI runners and macOS developer machines. It reads the
page up to `</head>`, skips HTML comments, and accepts any attribute
order and double, single, or no quotes. It is still a regular
expression rather than an HTML parser; `head-audit.py` parses the
page properly.

## Reference snippets

### `head-audit.spec.ts`

A Playwright `@playwright/test` spec that runs the chapter's full
head-correctness audit across a list of URLs, against the rendered
DOM. For each URL it asserts:

- exactly one `<title>` in `<head>`, non-empty and not a placeholder;
- exactly one absolute canonical in `<head>`;
- the indexing posture (every `X-Robots-Tag` header plus every robots
  and googlebot meta tag) matches the page's `shouldIndex` flag;
- `og:title`, `og:description`, `og:type`, and absolute `og:url` and
  `og:image` are present;
- a `twitter:card`, with `twitter:title` and `twitter:description` or
  the `og:` tags X falls back to;
- a single UTF-8 charset declaration (`<meta charset>` or the
  `http-equiv` form);
- absolute `hreflang` URLs, when hreflang is used. A missing
  `x-default` is a soft warning, since Google recommends it but does
  not require it.

Title and description lengths are soft warnings too. Robots directives
are parsed by the same code as `noindex-deployment-gate.js`.

Edit the `PAGES_TO_AUDIT` array at the top of the spec to point at
your staging URLs, or set `HEAD_AUDIT_PAGES` to a JSON file holding
the same array. Run with (after Setup):

```bash
npx playwright test head-audit.spec.ts

# Or with a page list from a file
HEAD_AUDIT_PAGES=pages.json npx playwright test head-audit.spec.ts
```

```json
[
  { "url": "https://staging.example.com/", "type": "home", "shouldIndex": true },
  { "url": "https://staging.example.com/account/settings", "type": "account", "shouldIndex": false }
]
```

### `generate-title.example.js`

ES module exporting `generateTitle(page, site)`, a per-page-type
title templating function for sites with too many pages to write
titles by hand. Falls back to `<h1> + brand` for unknown page types
and to brand-alone if both are missing, so no page ships with an
empty title. Stray whitespace in CMS fields is collapsed, and a
category with one product reads "1 Product".

`generate-title.example.test.js` is a colocated test file using
Node's built-in test runner (no test-framework dependency required).
Run with:

```bash
node --test generate-title.example.test.js
```

Asserts the chapter's two title invariants: every page type produces
a non-empty title, and distinct content does not collapse to the
same string.

### `og-image-route.example.tsx`

Reference Next.js App Router route handler that generates a 1200x630
Open Graph PNG from query-string parameters using `next/og`'s
`ImageResponse`. Drop the file at `app/api/og/route.tsx` in any
Next.js 14+ project. The route runs on the Edge runtime, so first-
fetch latency from social scrapers stays low. Without an `author`
parameter the footer shows the brand alone.

### `gsc-index-coverage.py`

A Python script that calls the Google Search Console URL Inspection
API for one or more URLs and emits the indexing verdict, robots.txt
state, Google-selected canonical, last crawl time, and related
fields as JSON. Designed for daily cron + observability pipeline
ingestion, so indexing-state regressions surface as graph movement
before they become traffic loss.

Requires extra dependencies not in this directory's
`requirements.txt`:

```bash
pip install google-api-python-client google-auth
```

You also need a Google Cloud service account with Search Console
property access. Pass the JSON key path with `--service-account` or
set `GOOGLE_APPLICATION_CREDENTIALS`.

```bash
python gsc-index-coverage.py --site https://www.example.com/ --url https://www.example.com/products/sample
python gsc-index-coverage.py --site sc-domain:example.com --urls-file urls.txt --output coverage.json
```

Exit codes: 0 every URL was inspected, 1 at least one inspection
failed (its record carries an `error` field), 2 usage or setup error
(missing or unreadable URL file or key, Google libraries not
installed).

## Wiring into CI

A typical pre-deployment workflow runs both scripts.

The Python auditor catches structural head problems on a representative
sample of pages from the production sitemap (run nightly or after every
deployment).

The Playwright gate runs against the staging build for every release
candidate, before the gate to production opens. The gate asserts that
no indexable URL has been accidentally marked `noindex`.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.
