# Chapter 13, HTTP Fundamentals for SEO

This directory contains the diagnostic scripts referenced in Chapter
13 of *SEO for Engineers, Volume 1*. The scripts cover the two
HTTP-layer checks engineering teams most often need beyond what a
standard crawler reports. Auditing the HTTP responses of a
population of URLs against the chapter's correctness rules, and
monitoring TLS certificate validity, chain completeness, SAN
coverage, and OCSP stapling status across a hostname inventory.

## Setup

The scripts in this chapter are Python. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `http-response-auditor.py`

A Python script that takes a sitemap URL or a list of URLs and
audits the HTTP response of each one against the rules Chapter 13
establishes as engineering standards.

The script runs the following checks against every URL.

- **Status code correctness.** Flags soft-404 patterns (200
  responses containing "not found" language or unusually short
  bodies), unexpected 404s on URLs declared in a sitemap, and
  improper use of 302 for canonicalization patterns.
- **Redirect chain length.** Walks redirects manually with a hop
  limit and reports chains longer than 1 hop. The threshold is
  configurable.
- **Redirect type correctness.** Flags 302 redirects on patterns
  that should be 301 (HTTP-to-HTTPS, www normalization, trailing
  slash normalization). The convention is configurable.
- **Cache header anomalies.** Flags `Cache-Control: no-store` on
  HTML responses (which disables bfcache), missing or stale
  `Last-Modified` and `ETag` headers, and `Cache-Control: max-age`
  values that are inappropriately long for HTML content.
- **Robots directive leakage.** Flags `X-Robots-Tag: noindex` in
  response headers and `<meta name="robots" content="noindex">`
  in HTML bodies. The most damaging staging-to-production failure
  mode the chapter describes.
- **Mixed content on HTTPS pages.** Scans rendered HTML for
  subresource references over `http://` on pages served via HTTPS.
- **Conditional request support.** Issues a follow-up request with
  `If-Modified-Since` and `If-None-Match` headers and verifies that
  the server returns 304 when the content has not changed.
- **Canonical signal conflicts.** Compares the `<link rel=
  "canonical">` element to any `Link: rel="canonical"` HTTP header
  and flags disagreements.
- **Content-Type correctness.** Verifies that HTML responses
  declare `text/html` with a charset, XML sitemaps declare
  `application/xml`, and robots.txt declares `text/plain`.

The script accepts either a sitemap URL or a URL list file. Sitemap
indexes are followed recursively. Output is structured JSON suitable
for CI gates or dashboard ingestion.

Usage:
Audit URLs from a sitemap
python http-response-auditor.py --sitemap https://example.com/sitemap.xml
Audit URLs from a file (one per line)
python http-response-auditor.py --urls urls.txt
Customize the redirect chain threshold (default is 1, single-hop only)
python http-response-auditor.py --sitemap <url> --max-redirect-hops 2
Skip conditional-request verification (faster, half the requests)
python http-response-auditor.py --sitemap <url> --skip-conditional
Limit the audit to N URLs (useful for large sitemaps)
python http-response-auditor.py --sitemap <url> --limit 500
Write a JSON report
python http-response-auditor.py --sitemap <url> --output report.json

The script exits non-zero if any error-severity finding is reported,
so it can be wired into CI as a deployment gate.

### `cert-and-stapling-monitor.py`

A Python script that connects to a list of hostnames over TLS and
verifies the certificate validity conditions Chapter 13 identifies
as the highest-risk failure modes for HTTPS infrastructure.

**Requires the `openssl` CLI on PATH** in addition to the Python
dependencies in `requirements.txt`. The script shells out to
`openssl s_client` for full-chain extraction and OCSP stapling
probing. Most macOS and Linux systems ship with it; on minimal
Docker images install it explicitly (`apk add openssl` on Alpine,
`apt-get install openssl` on Debian and Ubuntu).

The script runs the following checks against every hostname.

- **Certificate expiry window.** Reports days remaining until
  expiry. Configurable alerting thresholds (default 30, 14, and 7
  days) produce warnings or errors based on proximity to expiry.
- **SAN hostname coverage.** Verifies that the hostname being
  checked appears in the certificate's Subject Alternative Name
  list, accounting for single-label wildcards.
- **Chain completeness.** Connects without using any local
  intermediate cache and verifies that the server presents the
  full chain from leaf to a trusted root. Flags servers that send
  only the leaf certificate (the classic "works in Chrome on
  macOS, fails everywhere else" failure mode).
- **OCSP stapling status.** Requests a stapled OCSP response and
  reports whether the server returned a valid one. Reports the
  stapled response's `Next Update` timestamp so cache staleness
  can be detected.
- **Must-Staple extension presence.** Detects the TLS Feature
  extension (OID 1.3.6.1.5.5.7.1.24) and flags hostnames carrying
  Must-Staple certificates without working stapling, the most
  dangerous configuration the chapter describes.
- **Trust anchor age.** For certificates issued before March 15,
  2026, the maximum allowed validity is 398 days. For certificates
  issued on or after that date it drops to 200 days, then 100 days
  (March 15, 2027) and 47 days (March 15, 2029) per CA/Browser
  Forum Ballot SC-081v3. The script reports certificates whose
  notBefore-to-notAfter window exceeds the maximum applicable at
  the issuance date, which is a CA misissuance signal worth
  monitoring.

The script accepts a list of hostnames from a file or command line
and is suitable for running as a scheduled CI job or external
monitor.

Usage:
Check a single hostname
python cert-and-stapling-monitor.py --host example.com
Check multiple hostnames from a file
python cert-and-stapling-monitor.py --hosts-file hosts.txt
Customize the expiry warning thresholds
python cert-and-stapling-monitor.py --hosts-file hosts.txt --warn-days 21 --error-days 5
Write a JSON report
python cert-and-stapling-monitor.py --hosts-file hosts.txt --output report.json

The script exits non-zero if any error-severity finding is reported.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.