# Chapter 10, Internal Linking as a Graph Problem

This directory contains the diagnostic scripts referenced in Chapter
10 of *SEO for Engineers, Volume 1*. The scripts cover the two
internal-linking checks engineers most often need beyond standard
crawler outputs. Building the directed graph of a site's internal
links and identifying orphan pages and click-depth problems, and
verifying that paginated URL series remain crawlable through
Google-compatible `<a href>` link structures.

## Setup

This chapter has two toolchains, Python and Node.js. From this directory:

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

With `--html`, the script also writes a self-contained HTML dashboard
of the same report. It opens in any browser with no server or
dependencies (the report JSON is embedded in the page), renders the
depth distribution, reachability, and top-pages tables, and
auto-surfaces findings such as flat link equity, pages beyond the
depth threshold, orphans, and sitemap-only pages.

The crawl export CSV is expected to have at least two columns,
`source_url` and `target_url`. The legacy names `source` and
`destination` are also accepted for backward compatibility. An
`anchor` column is read if present but is not required.

The `source_url` / `target_url` convention matches the column
names used by Chapter 4's `link-graph-audit.py`, so a single
crawl export can feed both tools.

#### Usage

```bash
# Analyze a crawl export
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/

# Cross-reference against a sitemap to find sitemap-only orphans
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --sitemap https://example.com/sitemap.xml

# Include PageRank in the output
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --pagerank

# Write report to a file
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --output report.json

# Generate a visual HTML report alongside the JSON
python link-graph-analyzer.py --crawl crawl-export.csv --homepage https://example.com/ --pagerank --output report.json --html report.html
```

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

#### Usage

```bash
# Walk a paginated series starting from page 1
node pagination-crawlability-checker.js https://example.com/category/keyboards

# Cap the walk at 25 pages
node pagination-crawlability-checker.js https://example.com/category/keyboards --max-pages 25

# Require a link back to page 1 from each page
node pagination-crawlability-checker.js https://example.com/category/keyboards --require-page-one-link
```

The script exits non-zero if any high-severity issue is found, so it
can be wired into CI as a gate for pagination regressions.

## Reference snippets

### `pagination.example.tsx`

The numbered-pagination React component from the chapter. Renders
real `<a href>` links for first, last, and current ± 2 (with
ellipses between the windows), so Googlebot has a direct path to
any page in the series rather than walking prev/next sequentially.
Page 1 renders without a `?page=1` query string so the canonical
landing form stays `/category`.

### `infinite-scroll-pagination.example.html`

The full HTML + JS implementation of the "infinite scroll backed
by crawlable pagination" pattern. The initial server-rendered HTML
includes a real `<nav class="pagination">` with `<a href="?page=N">`
links Googlebot follows. JS-enabled users get the IntersectionObserver
overlay, which hides the static pagination and uses `history.pushState`
to keep the address bar in sync. Includes a `renderProductCard`
helper that HTML-escapes every user-controlled field before
`insertAdjacentHTML`, since the same sanitization principle from
chapter 9 (JSON-LD injection) applies to any HTML sink.

### `internal-link-validator.sh`

A Bash CI gate that reads a list of pages, fetches each one, and
asserts that every same-host internal link on the page returns HTTP
200. Pairs with `chapter-08-head-management/canonical-status-check.sh`:
the chapter 8 script checks one specific link per page (the canonical
tag), this one checks every internal anchor.

Usage:

```bash
./internal-link-validator.sh \
    --base-url https://example.com \
    --urls-file urls.txt
```

Portability. The script detects whether the local `grep` supports
PCRE (`-P`) and falls back to a Perl one-liner when it does not.
Same cross-platform pattern as `canonical-status-check.sh` in
chapter 8.

Same-host filter. The link extractor captures both relative paths
(`/foo`) and absolute URLs on the configured base host
(`https://example.com/foo`), then keeps only the same-host links
before requesting them.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.
