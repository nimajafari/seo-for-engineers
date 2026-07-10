# Chapter 6, Core Web Vitals as an Engineering Discipline

This directory contains the diagnostic scripts and RUM collector
referenced in Chapter 6 of *SEO for Engineers, Volume 1*. The
materials cover the three things engineers most often need to do
beyond what Lighthouse provides: collect field data from real users,
inspect the LCP four-part decomposition for a specific page, and
verify bfcache eligibility.

## Setup

The scripts in this chapter are Node.js. From this directory:

```bash
npm install
npx playwright install chromium
```

## Scripts

### `cwv-rum-collector.js`

A production-quality RUM collector for Core Web Vitals. Drop-in script
that uses the `web-vitals/attribution` build and sends metrics to a
configurable beacon endpoint, with the segmentation dimensions the
chapter recommends (page template, device type, connection type).

It collects LCP, INP, CLS, FCP, and TTFB with attribution data. For
LCP this includes the four sub-parts (TTFB, resource load delay,
resource load duration, element render delay) and the LCP element
identifier. For INP it includes the interaction type, the target, and
the three phases (input delay, processing duration, presentation
delay). For CLS it includes the largest shift target.

To use it, set `ANALYTICS_ENDPOINT` at the top of the file to your
beacon endpoint, then include the script with `type="module"` on every
page you want to measure.

```html
<script type="module" src="/cwv-rum-collector.js"></script>
```

If you do not have a bundler in your application, the script also
loads cleanly from a CDN via an import map. The header comment in the
file itself has the import-map example.

### `lcp-diagnostic.js`

A Playwright-based script that loads a URL in headless Chromium,
captures the LCP entry and the navigation timing entry, and computes
the four-part decomposition described in the chapter. Output is a
structured JSON report identifying the LCP element, the LCP resource
URL, the LCP time, the rating, and the four sub-parts in milliseconds.

The four-part values are approximations computed from
`PerformanceObserver` entries. They match what `web-vitals/attribution`
reports in production. For LCP elements that are text (no separate
resource fetch), the resource sub-parts are zero and the difference
flows into `elementRenderDelay`.

Usage:
node lcp-diagnostic.js https://example.com/
Multiple URLs
node lcp-diagnostic.js --urls https://example.com/ https://example.com/products/widget
URLs from a file (one per line, # for comments)
node lcp-diagnostic.js --urls-file urls.txt
Mobile viewport
node lcp-diagnostic.js --form-factor mobile https://example.com/

### `bfcache-eligibility-check.js`

A Playwright-based script that checks whether a URL is bfcache-eligible
in modern Chrome. It runs two checks. A passive header check for
`Cache-Control: no-store`, which is the most common bfcache blocker
that ships in a configuration mistake. And an active behavioral test
that navigates to the page, navigates away, navigates back, and reads
`performance.getEntriesByType('navigation')[0].notRestoredReasons` to
see what Chrome itself reported.

The behavioral test is the authoritative one. The header check is fast
and catches the most common case before the behavioral check runs.

Usage:
node bfcache-eligibility-check.js https://example.com/
Multiple URLs, JSON output
node bfcache-eligibility-check.js --urls https://example.com/ https://example.com/products/widget
URLs from a file (one per line, # for comments)
node bfcache-eligibility-check.js --urls-file urls.txt

Output identifies whether bfcache restored the page, and if not, which
of Chrome's `notRestoredReasons` were responsible.

### `delayed-third-party-loader.example.js`

A small browser-side ES module for the "delay non-critical third-party
scripts" pattern from the chapter. Exports
`loadAfterInteractionOrTimeout({ src, timeoutMs, events, async })`,
which loads a script tag exactly once after the user's first
interaction or after a fallback timeout, whichever fires first. The
load-once guarantee prevents the multi-load bug that happens when a
naive `{ once: true }`-only implementation receives two different
events (e.g. click then scroll).

The load-once invariant is locked in by
`delayed-third-party-loader.example.test.js` (run with `npm test`, which
uses the built-in `node --test` runner with stubbed browser globals and
needs no extra dependency).

### `lighthouse-ci.github-actions.yml`

A sample GitHub Actions workflow that deploys to staging on every PR
to `main` and runs Lighthouse CI against the deployed URLs. Pairs
with a project-level `.lighthouserc.yml`. Copy to
`.github/workflows/lighthouse.yml` in your repo and adapt the deploy
step, URL list, and config path to your environment.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.