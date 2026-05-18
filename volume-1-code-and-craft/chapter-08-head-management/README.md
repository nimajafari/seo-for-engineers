# Chapter 8, Meta Tags, Canonical Tags, and Head Management

This directory contains the diagnostic scripts referenced in Chapter 8
of *SEO for Engineers, Volume 1*. The scripts audit the contents of
the `<head>` element across a site and provide a CI gate against the
most expensive head-management failure mode: accidental `noindex`
deployments to production.

## Scripts

### `head-audit.py`

A Python audit that fetches a URL (or a list of URLs from a sitemap)
and inspects every page's `<head>` against the checklist from
Chapter 8.

For each page, the audit reports findings in three severity buckets.

**High severity.** Missing `<title>`, empty `<title>`, multiple
`<title>` elements, missing `<link rel="canonical">`, multiple
canonical tags, canonical URL pointing to a non-200 response (when
`--check-canonical-status` is set), `noindex` directive on a URL the
caller flagged as indexable, and the `noindex` plus canonical-to-an-
indexable-URL conflict from Failure Mode 5.

**Medium severity.** Relative canonical URL, canonical host that does
not match the page host, generic title values (`Untitled`, `Home`, the
site brand alone), and missing `<meta name="description">`.

**Low severity.** Missing `og:title`, missing `og:image`, missing
`og:url`, missing X (Twitter) card markup, and viewport meta tag
missing or misconfigured.

The script reads URLs from one of three sources. A single URL via
`--url`. A newline-separated list of URLs via `--urls-file`. Or a
sitemap or sitemap index via `--sitemap`, in which case the script
parses the sitemap, optionally limited by `--limit`.

Usage:
Audit a single URL
python head-audit.py --url https://example.com/
Audit a list of URLs
python head-audit.py --urls-file urls.txt
Audit pages from a sitemap (random sample of 50)
python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50
Also verify that each canonical URL returns HTTP 200
python head-audit.py --sitemap https://example.com/sitemap.xml --limit 50 --check-canonical-status
JSON output to a file
python head-audit.py --url https://example.com/ --output report.json

Install:
pip install -r requirements.txt

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

First, an HTTP-level check. The response's `X-Robots-Tag` header is
inspected. If the header contains `noindex` (case-insensitive), the
URL fails.

Second, a rendered-DOM check. The page is loaded in headless
Chromium and the rendered DOM is inspected for `<meta name="robots">`
and `<meta name="googlebot">` tags containing `noindex`. The
rendered-DOM check catches the case where `noindex` is injected by
client-side JavaScript after initial render, which the HTTP check
would miss.

Usage:
node noindex-deployment-gate.js --urls https://staging.example.com/ https://staging.example.com/products/sample
From a newline-separated file
node noindex-deployment-gate.js --urls-file staging-urls.txt

Exits non-zero if any URL has `noindex` set. Designed to be wired
directly into a deployment pipeline as a required check.

Install:

```bash
npm install
npx playwright install chromium
```

### `canonical-status-check.sh`

A small Bash script that reads a list of URLs and verifies each
URL's `<link rel="canonical">` tag points at a URL returning HTTP
200. Catches canonical drift, where a canonical continues pointing
at a URL that has since been redirected, removed, or otherwise
stopped returning 200. Designed to run in CI as a regression gate.

Usage:

```bash
./canonical-status-check.sh urls.txt
```

`urls.txt` should contain one URL per line; blank lines and lines
starting with `#` are skipped. Exits 1 if any canonical issue is
found, 0 otherwise.

Portability. The script detects whether the local `grep` supports
PCRE (`-P`) and falls back to a Perl one-liner when it does not.
This means the same file runs on Linux CI runners (GNU grep
available) and on macOS developer machines (BSD grep, no `-P`)
without changes.

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