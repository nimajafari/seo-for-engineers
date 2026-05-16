# Chapter 3, Indexing, Canonicalization, and Duplicate Detection

This directory contains the diagnostic scripts referenced in Chapter 3
of *SEO for Engineers, Volume 1*. The scripts help you audit canonical
tags at scale and detect soft 404s before they degrade your index
coverage.

## Scripts

### `canonical-audit.py`

Audits the canonical tags on a list of URLs and flags the failure modes
described in the chapter.

For each URL the script fetches the page, parses every `<link rel="canonical">`
element in the document, and reports the following.

- Missing canonical tag.
- Multiple canonical tags on the same page.
- Relative canonical URL (Google requires absolute URLs).
- Canonical tag built from the request URL, containing tracking
  parameters (`utm_*`, `fbclid`, `gclid`, `session_id`, and similar).
- Canonical points to a URL on a different host.
- Page URL and canonical URL differ after normalization (the page is
  not self-canonical and may be a duplicate).

The script does not follow the canonical link to verify that the target
returns a 200 status. That is intentional. Following can be expensive on
large audits and is a separate concern. Use the canonical target as the
input for a subsequent run if you want to verify the destination.

Usage:
Single URL
python canonical-audit.py https://example.com/page
Batch mode, one URL per line in a text file, CSV output
python canonical-audit.py --urls urls.txt --csv report.csv

### `soft-404-detector.py`

Scans a list of URLs for the soft-404 patterns described in the chapter.
For each URL it checks the HTTP status, counts visible words, and looks
for characteristic soft-404 phrases. URLs that return 200 but match the
soft-404 signature are flagged for manual review.

What the script considers a soft 404 candidate.

- Returns HTTP 200.
- Visible word count below a configurable threshold (default 50).
- Contains one or more characteristic phrases ("no results found",
  "page not found", "no longer available", "currently unavailable",
  "this product has been discontinued", etc.).

The thresholds and phrase list are configurable via command-line flags
or by editing the constants at the top of the script.

The script does not assume any specific definition of "soft 404."
Google's classification is based on content analysis and may pick up
patterns this script does not. Treat the output as a starting list for
manual review, not as ground truth.

Usage:
Single URL
python soft-404-detector.py https://example.com/category/empty
Batch mode with CSV output
python soft-404-detector.py --urls urls.txt --csv report.csv
Custom word threshold
python soft-404-detector.py --urls urls.txt --csv report.csv --min-words 100

### Installing

Both scripts require Python 3.10 or later. Install dependencies once.
pip install -r requirements.txt

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.