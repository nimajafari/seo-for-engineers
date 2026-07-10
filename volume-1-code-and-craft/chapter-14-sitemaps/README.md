# Chapter 14, Sitemaps as a Backend Responsibility

This directory contains the diagnostic scripts referenced in Chapter
14 of *SEO for Engineers, Volume 1*. The scripts cover the two
sitemap-layer checks engineering teams most often need beyond what a
standard crawler reports. Auditing a sitemap (or sitemap index)
against the twelve failure modes the chapter catalogues, and
monitoring the accuracy of `<lastmod>` values against actual page
content over time.

## Setup

The scripts in this chapter are Python. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `sitemap-auditor.py`

A Python script that takes a sitemap URL or a sitemap index URL and
audits the response and the contained URLs against the correctness
rules Chapter 14 establishes as engineering standards.

The script runs the following checks at the sitemap level.

- **Content-Type correctness.** Verifies that the sitemap is served
  with an `application/xml` (or compatible) `Content-Type`. Some
  crawlers will fail to parse a sitemap served as `text/html` or
  `application/octet-stream`.
- **Gzip handling.** Detects gzip-compressed sitemaps, decompresses
  them transparently, and validates the decompressed payload against
  the 50 MB uncompressed-size limit.
- **Well-formed XML.** Parses the sitemap with `lxml` in a hardened
  configuration (no external entity resolution, no network entity
  loading) and reports parse errors.
- **URL count.** Flags sitemaps that exceed the 50,000-URL
  per-sitemap limit. Sitemap indexes recurse into their children and
  are checked individually.
- **`<lastmod>` format validity.** Validates each `<lastmod>` value
  against the W3C datetime subset of ISO 8601 (date-only or full
  datetime with timezone). Malformed datetimes invalidate the entry.
- **`<lastmod>` distribution sanity.** Catches the deploy-timestamp
  bug where every URL in the sitemap carries an identical `<lastmod>`
  equal to the last build time. If the spread between the earliest
  and latest `<lastmod>` across a sitemap of more than ten URLs is
  under one hour, the script flags it as a likely freshness-signal
  failure.

The script runs the following checks against a sample of URLs from
each sitemap.

- **Robots.txt allowance.** Fetches `robots.txt` from the sitemap's
  origin and asserts that each sampled URL is permitted for crawling.
  URLs declared in a sitemap but disallowed in `robots.txt` are
  wasted entries and produce Search Console errors.
- **HTTP status.** Issues a GET against each sampled URL with manual
  redirect handling, walks any redirect chain to its terminus, and
  reports the final status. Non-200 terminal status codes are
  flagged.
- **Redirect chain length.** Reports URLs that resolve only after
  more than one redirect hop. The threshold is configurable.
- **`noindex` directive.** Inspects the response for
  `X-Robots-Tag: noindex` in the HTTP headers and
  `<meta name="robots" content="noindex">` in the HTML body. Either
  one on a URL submitted in a sitemap is a hard error.
- **Canonical tag match.** Extracts the `<link rel="canonical">`
  element from the page and compares it against the sitemap URL
  after normalization. Trailing-slash and host-case mismatches are
  the dominant pattern. The canonical form is configurable.
- **Staging-domain leak.** Flags sitemap URLs whose host contains
  any of the standard staging patterns (`staging`, `stage`, `dev`,
  `test`, `preview`, `.local`). This catches the deploy-pipeline
  bug where staging URLs leak into the production sitemap.

The script accepts a sitemap URL or sitemap index URL. Indexes are
followed recursively. Output is structured JSON suitable for CI
gates or dashboard ingestion.

Usage.
Audit a sitemap with default settings
python sitemap-auditor.py --sitemap https://example.com/sitemap.xml
Audit a sitemap index and increase the per-sitemap sample size
python sitemap-auditor.py --sitemap https://example.com/sitemap.xml --sample 200
Tighten the redirect chain threshold to zero hops
python sitemap-auditor.py --sitemap https://example.com/sitemap.xml --max-redirect-hops 0
Enforce a trailing-slash canonical form during normalization
python sitemap-auditor.py --sitemap https://example.com/sitemap.xml --canonical-form trailing_slash
Write a JSON report
python sitemap-auditor.py --sitemap https://example.com/sitemap.xml --output report.json

The script exits non-zero if any error-severity finding is reported,
so it can be wired into CI as a deployment gate.

### `sitemap-freshness-monitor.py`

A Python script that validates whether `<lastmod>` values in a
sitemap correspond to actual content changes, by hashing the visible
page content of a sample of URLs and comparing against a JSON state
file across runs.

The script reports the two failure modes that pure-static analysis
cannot catch.

- **Overactive `<lastmod>`.** A URL's `<lastmod>` advanced between
  runs but the hashed visible content did not change. This is the
  signature of a sitemap generator deriving `<lastmod>` from a
  deploy timestamp or a row-level `updated_at` rather than from a
  content-level timestamp.
- **Stale `<lastmod>`.** The hashed visible content changed between
  runs but `<lastmod>` did not advance. This is the signature of a
  sitemap generator missing a content-change trigger, or of editorial
  edits that bypass the `content_updated_at` update path.

The script also reports `<lastmod>` format validity per URL and
flags URLs with no `<lastmod>` for informational tracking.

State is persisted as JSON between runs so the script can run on a
schedule (daily, weekly) and accumulate signal. A custom CSS or
XPath selector can be passed to scope the content hash to a specific
region of the page if the default heuristic (prefer `<main>` or
`<article>`, strip `script`, `style`, `nav`, `header`, `footer`,
`aside`, `noscript`) is too broad or too narrow.

Usage.
First run, populates the state file
python sitemap-freshness-monitor.py --sitemap https://example.com/sitemap.xml
Subsequent runs compare against the state file
python sitemap-freshness-monitor.py --sitemap https://example.com/sitemap.xml
Scope the content hash to a specific selector
python sitemap-freshness-monitor.py 
--sitemap https://example.com/sitemap.xml 
--selector "article.post-body"
Use a custom state file location
python sitemap-freshness-monitor.py 
--sitemap https://example.com/sitemap.xml 
--state-file /var/lib/seo-tooling/freshness-state.json
Write a JSON report
python sitemap-freshness-monitor.py 
--sitemap https://example.com/sitemap.xml 
--output report.json

The script exits non-zero if any error-severity finding is reported.
Overactive and stale `<lastmod>` findings are surfaced as warnings,
which is the appropriate severity for a signal that must be
investigated but is not by itself a deployment blocker.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.