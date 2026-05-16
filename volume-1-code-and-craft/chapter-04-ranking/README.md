# Chapter 4, Ranking Signals That Engineering Controls

This directory contains the diagnostic scripts referenced in Chapter 4
of *SEO for Engineers, Volume 1*. The scripts let you analyze your
site's internal link graph as a graph and pull field Core Web Vitals
data from the same source Google's ranking systems use.

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
this shape directly, or close to it.

```csv
source_url,target_url,target_status_code
https://example.com/,https://example.com/about,200
https://example.com/,https://example.com/old-page,301
https://example.com/products,https://example.com/products/widget,200
```

Usage:
python link-graph-audit.py --crawl crawl.csv --homepage https://example.com/ --out report.csv

The script writes a per-URL CSV with columns for PageRank, in-degree,
out-degree, click depth, orphan flag, and broken-link count. It also
prints a summary to stderr.

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
and "poor" buckets for each metric. Running this monthly creates the
longitudinal record described in the Manager Lens section of the
chapter.

You will need a Google API key with the CrUX API enabled. Get one from
the Google Cloud Console. Pass it via the `CRUX_API_KEY` environment
variable or the `--key` flag.

Usage:
export CRUX_API_KEY=your_api_key_here
Single URL
python crux-fetcher.py https://example.com/
Batch mode, one URL per line in a text file, CSV output
python crux-fetcher.py --urls urls.txt --csv report.csv
Phone form factor (default), desktop, or tablet
python crux-fetcher.py --urls urls.txt --csv report.csv --form-factor DESKTOP

URLs without enough traffic to have CrUX data will return a 404 from
the API. The script logs these and marks them with `has_data=no` in
the CSV. For low-traffic pages, you can fall back to origin-level data
by passing `--origin` to query the domain-level aggregate instead.

### Installing

Both scripts require Python 3.10 or later. Install dependencies once.
pip install -r requirements.txt

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.