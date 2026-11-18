# Chapter 4, Ranking Signals That Engineering Controls

This directory contains the diagnostic scripts referenced in Chapter 4
of *SEO for Engineers, Volume 1*. The scripts let you analyze your
site's internal link graph as a graph and pull field Core Web Vitals
data from the same source Google's ranking systems use.

## Setup

The scripts in this chapter are Python. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `link-graph-audit.py`

Treats a crawl export as the directed graph it is. Computes PageRank,
finds orphans, calculates click depth from the homepage, and counts
broken internal links per source page.

The script is the working implementation of the audit pattern described
in the Internal Link Architecture section of the chapter. Output is a
per-URL CSV that engineering teams can use to prioritize structural
fixes (which orphaned pages to link to, which deep pages to surface
through editorial cross-links, which broken links to repair).

Input format is a CSV with three columns. `source_url`, `target_url`,
and `target_status_code`. One row per internal link found during the
crawl. Most commercial crawlers (Screaming Frog, Sitebulb) can export
this shape directly, or close to it. The bare name `status_code` is
also accepted as an alias for `target_status_code`, matching the
inline snippet in Chapter 4.

```csv
source_url,target_url,target_status_code
https://example.com/,https://example.com/about,200
https://example.com/,https://example.com/old-page,301
https://example.com/products,https://example.com/products/widget,200
```

Links are classified by the target's status code:

- **2xx** links form the graph used for PageRank and click depth.
- **3xx** links are counted as `redirect_link_count`. They work but cost
  a hop, so they're worth updating. They are *not* broken.
- **4xx/5xx**, or no response at all (crawlers export timeouts as status
  0), are counted as `broken_link_count`.

Self-links are ignored, and rows with an empty URL are dropped with a
warning. The homepage is matched with or without a trailing slash, so
`https://example.com` finds `https://example.com/` in the crawl.

An orphan is a page that no other page links to. A crawl that follows
links can only see orphans that were crawl seeds, so pass `--known-urls`
(for example a sitemap export, one URL per line) to also catch pages no
internal link reaches at all. Those rows are appended to the report with
blank PageRank and depth.

Usage:

```bash
python link-graph-audit.py --crawl crawl.csv --homepage https://example.com/ --out report.csv

# Also find pages in the sitemap that nothing links to
python link-graph-audit.py --crawl crawl.csv --homepage https://example.com/ \
  --out report.csv --known-urls sitemap-urls.txt
```

The script writes a per-URL CSV with columns for PageRank, in-degree,
out-degree, click depth, orphan flag, broken-link count, and
redirect-link count. It also prints a summary to stderr, including how
many pages can't be reached from the homepage through 2xx links.

The PageRank values are useful as relative priorities, not as absolute
authority numbers. A URL with PageRank 0.0021 is not "worth 0.21% of
the site's authority" in any meaningful sense. It is the rank within
this audit. Use PageRank as a comparison tool, not as a calibrated
measurement.

### `crux-fetcher.py`

Fetches field Core Web Vitals data from the [Chrome User Experience
Report (CrUX) API](https://developer.chrome.com/docs/crux/api/) for a
list of URLs. This is the same data source Google's ranking systems use
for the Page Experience signal.

Output is a CSV with LCP, INP, and CLS values at the 75th percentile,
along with the percentage of visits in the "good", "needs improvement",
and "poor" buckets for each metric. Each row also carries
`collection_period_end`, the last day of the trailing 28-day CrUX
window, which dates the data when you run this monthly to build the
longitudinal record described in the Manager Lens section of the
chapter.

You will need a Google API key with the CrUX API enabled. Get one from
the Google Cloud Console. Pass it via the `CRUX_API_KEY` environment
variable or the `--key` flag. The key is sent in the `X-Goog-Api-Key`
header rather than the URL, so it never shows up in error messages, the
console or the CSV.

Usage:

```bash
export CRUX_API_KEY=your_api_key_here

# Single URL
python crux-fetcher.py https://example.com/

# Batch mode, one URL per line in a text file, CSV output
python crux-fetcher.py --urls urls.txt --csv report.csv

# Restrict to a form factor (default is all form factors combined)
python crux-fetcher.py --urls urls.txt --csv report.csv --form-factor DESKTOP
```

URLs without enough traffic to have CrUX data will return a 404 from
the API. The script logs these and marks them with `has_data=no` in
the CSV. For low-traffic pages, you can fall back to origin-level data
by passing `--origin` to query the domain-level aggregate instead. In a
batch, each origin is queried once and shared across its URLs, so it
doesn't use up the API's per-minute quota.

The script exits 1 if any URL hit an API or network error, and exits 2
for a usage problem (no key, or an unreadable or empty `--urls` file).

## Tests

After Setup, from this directory:

```bash
python3 -m pytest -q
```

Or from the repo root: `make test-chapter-04-ranking`. The CrUX API is
mocked, so no key or network access is needed.

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.