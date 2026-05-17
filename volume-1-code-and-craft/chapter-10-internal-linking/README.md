# Chapter 10, Internal Linking as a Graph Problem

This directory contains the diagnostic scripts referenced in Chapter
10 of *SEO for Engineers, Volume 1*. The scripts cover the two
internal-linking checks engineers most often need beyond standard
crawler outputs. Building the directed graph of a site's internal
links and identifying orphan pages and click-depth problems, and
verifying that paginated URL series remain crawlable through
Google-compatible `<a href>` link structures.

## Scripts

### `link-graph-analyzer.py`

A Python script that takes a crawl export CSV (Screaming Frog,
Sitebulb, Lumar, or any tool that exports source-destination link
pairs) builds the NetworkX directed graph from Chapter 10, and
computes the structural metrics the chapter identifies as actionable.

**Note on scope.** A separate script `link-graph-audit.py` lives in
the Chapter 4 directory and covers PageRank computation, orphan
detection, and depth analysis at a general level. This Chapter 10
script focuses on the orphan-and-depth analysis specifically, with a
more detailed breakdown of click-depth distribution, severity
buckets, and the cross-reference between sitemap-listed URLs and
internally-linked URLs that the chapter introduces. The two scripts
complement rather than duplicate each other.

The script computes the following.

- Total pages and total internal links.
- Click depth from the homepage for every reachable page, with
  distribution buckets (depth 1, 2, 3, 4, 5+).
- Pages with zero inbound internal links (orphans by graph
  definition).
- Pages in the sitemap but absent from the crawl graph (orphans by
  sitemap-vs-graph diff).
- Pages in the graph but unreachable from the homepage.
- Top pages by in-degree (most internally linked).
- Top pages by out-degree (most outbound internal links).
- Optional PageRank computation across the internal graph, normalized
  so values sum to 1.

The crawl export CSV is expected to have at least two columns,
`source` and `destination`. An `anchor` column is read if present
but is not required.

Usage:
Analyze a crawl export
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/
Cross-reference against a sitemap to find sitemap-only orphans
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --sitemap https://example.com/sitemap.xml
Include PageRank in the output
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --pagerank
Write report to a file
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --output report.json

Install:
pip install -r requirements.txt

### `pagination-crawlability-checker.js`

A Playwright-based script that walks a paginated URL series and
verifies the conditions Chapter 10 establishes as required for
Google-friendly pagination.

For each page in the series the script verifies the following.

- The page returns HTTP 200.
- The page has a self-referencing canonical tag, not a canonical
  pointing to page 1.
- The page has at least one crawlable `<a href>` link to the next
  page (or, on the last page, no broken next link).
- The pagination links use real anchor elements with `href`
  attributes, not buttons or JavaScript-driven navigation.
- The URL does not rely on a fragment identifier (`#`) for the
  page parameter.
- (Optional) The page links back to page 1 of the series, as Google's
  documentation suggests as a hint.

The script walks the series starting from page 1 and follows the
detected next-page links until it can find no further page, an
infinite-loop protection limit is reached, or an explicit
`--max-pages` cap is hit.

Usage:
Walk a paginated series starting from page 1
node pagination-crawlability-checker.js https://example.com/category/keyboards
Cap the walk at 25 pages
node pagination-crawlability-checker.js https://example.com/category/keyboards --max-pages 25
Require a link back to page 1 from each page
node pagination-crawlability-checker.js https://example.com/category/keyboards --require-page-one-link

The script exits non-zero if any high-severity issue is found, so it
can be wired into CI as a gate for pagination regressions.

Install:
npm install
npx playwright install chromium

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.
