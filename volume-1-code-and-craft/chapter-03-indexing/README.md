# Chapter 3, Indexing, Canonicalization, and Duplicate Detection

This directory contains the diagnostic scripts referenced in Chapter 3
of *SEO for Engineers, Volume 1*. The scripts help you audit canonical
tags at scale and detect soft 404s before they degrade your index
coverage.

## Setup

The scripts in this chapter are Python. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `canonical-audit.py`

Audits the canonical tags on a list of URLs and flags the failure modes
described in the chapter.

For each URL the script fetches the page and collects its canonicals
from two sources Google honors: `<link rel="canonical">` elements in
`<head>`, and the HTTP `Link: <…>; rel="canonical"` header (the only
option for PDFs and other non-HTML files). It reports the following.

- Missing canonical (neither source has one).
- Canonical `<link>` outside `<head>`, which Google ignores. The HTML is
  parsed with html5lib, which builds the same tree a browser does, so
  this also catches the subtle case: an element that isn't allowed in
  `<head>` (an `<img>`, `<iframe>` or `<div>`, often injected by a tag
  manager) closes `<head>` early, and every tag after it lands in
  `<body>`.
- Conflicting canonicals: more than one, pointing to different targets,
  across tags and headers. Google may ignore all of them. Duplicates with
  the same target are reported separately.
- Relative canonical URL. Google supports these but recommends absolute
  URLs. The href is resolved against the page URL (or `<base href>`) and
  still goes through every check below.
- Canonical that isn't an http(s) URL.
- Canonical tag built from the request URL, containing tracking
  parameters (`utm_*`, `fbclid`, `gclid`, `session_id`, and similar).
- Canonical points to a URL on a different host.
- Page URL and canonical URL differ after normalization (the page is
  not self-canonical and may be a duplicate). Normalization lowercases
  the scheme and host, IDNA-encodes the host, drops default ports, treats
  an empty path as `/`, ignores a trailing slash, and percent-encodes
  the path consistently. So `https://example.com` matches
  `https://example.com/`, and `/café` matches `/caf%C3%A9`. Tracking
  parameters are stripped before this comparison, so a page reached with
  `?utm_source=…` that canonicalizes to the clean URL is treated as
  correct, not flagged.

The script does not follow the canonical link to verify that the target
returns a 200 status. That is intentional. Following can be expensive on
large audits and is a separate concern. Use the canonical target as the
input for a subsequent run if you want to verify the destination.

Usage:

```bash
# Single URL, JSON output
python canonical-audit.py https://example.com/page

# Batch mode, one URL per line in a text file, CSV output
python canonical-audit.py --urls urls.txt --csv report.csv
```

The output includes `canonical_resolved` (the absolute target) and
`canonical_source` (`html` or `header`). The script exits 1 if any URL
has an issue or a request error, so it can gate CI, and exits 2 for a
usage problem such as an unreadable or empty `--urls` file.

### `soft-404-detector.py`

Scans a list of URLs for the soft-404 patterns described in the chapter.
Only URLs that end in HTTP 200 are considered, since a real 4xx is not a
soft 404. A URL is a suspect if any of these signals fires, and the
`signals` field says which ones did:

- `thin_content`: visible word count below a configurable threshold
  (default 50). Han and Japanese kana characters count as one word each,
  so Chinese and Japanese pages aren't all flagged as thin.
- `error_phrase`: the visible text contains a characteristic phrase
  ("no results found", "page not found", "no longer available",
  "currently unavailable", "this product has been discontinued", and so
  on).
- `redirected_to_root`: a non-root URL redirected to the site's home
  page, the classic way removed pages get "handled". Google treats these
  redirects as soft 404s.

Two or more signals make a stronger candidate than one. For example, a
long product page that only mentions "out of stock" trips
`error_phrase` alone.

The thresholds and phrase list are configurable via command-line flags
or by editing the constants at the top of the script.

The script does not assume any specific definition of "soft 404."
Google's classification is based on content analysis and may pick up
patterns this script does not. Treat the output as a starting list for
manual review, not as ground truth.

Usage:

```bash
# Single URL
python soft-404-detector.py https://example.com/category/empty

# Batch mode with CSV output
python soft-404-detector.py --urls urls.txt --csv report.csv

# Custom word threshold and phrase list (one phrase per line)
python soft-404-detector.py --urls urls.txt --csv report.csv --min-words 100 --phrases phrases.txt
```

The script exits 1 if any URL is a suspect or errored, and exits 2 for a
usage problem such as an unreadable `--urls` or `--phrases` file.

### `canonical-enforcement.nginx.conf`

A reference nginx server configuration that enforces a single canonical
URL shape across three dimensions: protocol (HTTP -> HTTPS), host
(non-www -> www), and trailing-slash policy (strip non-root trailing
slashes for non-directory URLs). Adapt the domain and certificate paths
to your environment. URL casing is handled at the application layer,
not here.

Every server listens on IPv6 as well as IPv4, since Googlebot may crawl
over IPv6 when the domain has AAAA records. The HTTPS servers enable
HTTP/2 (`http2 on;` needs nginx 1.25.1 or later), without which nginx
serves HTTP/1.1 only. The config was verified in nginx 1.30: correct
301s, HTTP/2 negotiated, query strings kept when the slash is stripped,
and real directories left alone.

## Tests

After Setup, from this directory:

```bash
python3 -m pytest -q
```

Or from the repo root: `make test-chapter-03-indexing`. The tests serve
canned pages, headers and redirects from a local HTTP server, so they
run offline.

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.