# Chapter 6, Core Web Vitals as an Engineering Discipline

This directory contains the diagnostic scripts and RUM collector
referenced in Chapter 6 of *SEO for Engineers, Volume 1*. The
materials cover the three things engineers most often need to do
beyond what Lighthouse provides: collect field data from real users,
inspect the LCP four-part decomposition for a specific page, and
verify bfcache eligibility.

## Setup

The scripts in this chapter are Node.js (20 or newer). From this
directory:

```bash
npm install
npx playwright install chromium
npm test
```

`npx playwright install chromium` downloads both the headless shell
that `lcp-diagnostic.js` uses and the full Chromium build that
`bfcache-eligibility-check.js` needs. `npm test` runs the unit tests
with the built-in `node --test` runner; they need neither Playwright
nor `web-vitals` installed.

Both Playwright scripts use the same exit codes: 0 when every URL
passes, 1 when at least one URL fails the check, 2 for a usage error
or a URL that could not be checked (and none failed).

## Scripts

### `cwv-rum-collector.js`

A production-quality RUM collector for Core Web Vitals. Drop-in script
that uses the `web-vitals/attribution` build (v6) and sends metrics to a
configurable beacon endpoint, with the segmentation dimensions the
chapter recommends (page template, device type, connection type).

It collects LCP, INP, CLS, FCP, and TTFB with attribution data. For
LCP this includes the four sub-parts (TTFB, resource load delay,
resource load duration, element render delay) and the LCP element
identifier. For INP it includes the interaction type, the target, and
the three phases (input delay, processing duration, presentation
delay). For CLS it includes the largest shift target.

Every beacon also carries the metric's `id`, `delta`, and
`navigationType`. A metric can be reported more than once for the same
page view: CLS and INP are reported again when they grow after the tab
was hidden and shown, and every bfcache restore starts new metric
instances. Keep the last `value` per `id` (or sum `delta` per `id`) in
your backend; summing `value` double-counts. `navigationType` separates
`back-forward-cache` and `prerender` page views, which are nearly
instant, from ordinary navigations.

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

LCP entries are only delivered to a `PerformanceObserver`;
`performance.getEntriesByType('largest-contentful-paint')` is always
empty. The script installs the observer before any page script runs.
The four sub-parts use the same arithmetic as `web-vitals/attribution`
v6, so they add up to the LCP time and match what the RUM collector
reports. For LCP elements that are text (no separate resource fetch),
the resource sub-parts are zero and the difference flows into
`elementRenderDelay`.

This is a lab run on your machine without CPU or network throttling.
Use it to see which sub-part dominates, and the field data from the
RUM collector or CrUX for the numbers that count.

Usage:

```bash
node lcp-diagnostic.js https://example.com/

# Multiple URLs
node lcp-diagnostic.js --urls https://example.com/ https://example.com/products/widget

# URLs from a file (one per line, # for comments)
node lcp-diagnostic.js --urls-file urls.txt

# Mobile emulation (Pixel 7); the default is desktop
node lcp-diagnostic.js --form-factor mobile https://example.com/
```

The exit code is 1 when any URL is rated needs-improvement or poor.

### `bfcache-eligibility-check.js`

A Playwright-based script that checks whether a URL is bfcache-eligible
in modern Chrome. It runs two checks. A passive header check for
`Cache-Control: no-store`, the most common bfcache blocker that ships
in a configuration mistake: Chrome refuses to restore a `no-store` page
whenever a cookie changed while the user was away, and other browsers
may refuse it outright. And an active behavioral test that loads the
page, navigates away, goes back, and checks whether Chrome restored it.

The behavioral test is the authoritative one for Chrome. Three details
make it give a real answer:

- Playwright launches Chromium with `--disable-back-forward-cache`, and
  its default headless shell cannot use bfcache at all. The script
  removes the flag and runs the full Chromium build in headless mode.
- A page restored from bfcache keeps its original navigation entry
  (type `navigate`), so the script detects a restore from the
  `pageshow` event's `persisted` flag.
- When the page was not restored, the reasons come from the DevTools
  protocol (`Page.backForwardCacheNotUsed`, the same source as the
  DevTools bfcache tester), with the page's `notRestoredReasons` as a
  fallback. The latter often says only `masked`.

Usage:

```bash
node bfcache-eligibility-check.js https://example.com/

# Multiple URLs, JSON output
node bfcache-eligibility-check.js --urls https://example.com/ https://example.com/products/widget

# URLs from a file (one per line, # for comments)
node bfcache-eligibility-check.js --urls-file urls.txt

# Visit a page of your own site in between (default: about:blank)
node bfcache-eligibility-check.js --away https://example.com/account https://example.com/
```

Use `--away` with a page that sets cookies, as a logged-in page often
does, to see whether a `no-store` page survives the cookie change.

Output identifies whether bfcache restored the page, and if not, the
reasons Chrome gave. A `no-store` page is never reported as eligible,
even when Chrome restored it, because the cookie condition and other
browsers make that restore unreliable.

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
with a project-level `lighthouserc.yml` (chapter 5 has a starter).
Copy to `.github/workflows/lighthouse.yml` in your repo and adapt the
deploy step, URL list, and config path to your environment. The deploy
step fails the job when the deploy script fails or prints no URL, and
reports stay in a workflow artifact instead of public storage.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.