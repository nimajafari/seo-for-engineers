# Chapter 5, JavaScript Rendering and the Crawlability Challenge

This directory contains the diagnostic scripts and CI templates
referenced in Chapter 5 of *SEO for Engineers, Volume 1*. The materials
help you verify that your rendering strategy actually delivers content
to crawlers, and that your Speculation Rules API configuration is not
quietly setting fire to your analytics, A/B testing, or origin load.

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

## Scripts and templates

### `rendering-strategy.spec.ts`

A Playwright test suite that verifies the SEO-critical content of a
page. It runs two checks against every URL. First, in a browser context
with JavaScript disabled (`test.use({ javaScriptEnabled: false })`),
which approximates the initial HTTP response that Googlebot processes in
wave one. Second, with JavaScript enabled and the page allowed to reach
`networkidle`, which approximates what Googlebot's wave-two render
produces.

Each check asserts on:

- `<h1>` is present and not empty.
- `<title>` is present and not a static framework placeholder.
- No `noindex` in a `robots` or `googlebot` meta tag. A `noindex` in the
  initial HTML stops Google before it renders, so JavaScript that removes
  it later never gets the chance.
- Exactly one `<link rel="canonical">`, with an absolute URL on the same
  host as the page (the final URL after redirects).
- At least one JSON-LD `<script>` block, and every block parses as valid
  JSON.

A client-rendered page typically passes the second check and fails the
first, which is the dependency on the rendering queue the chapter warns
about.

This is the working version of the test example in the chapter,
extended with the practical assertions you actually want in CI.

To use it, edit the `DEFAULT_URLS` array at the top of the file with
the URLs you want to verify (typically staging), or pass them in
`SEO_TEST_URLS`. Then, after Setup, run:

```bash
npx playwright test rendering-strategy.spec.ts

# URLs from the environment, separated by spaces or commas
SEO_TEST_URLS="https://staging.example.com/ https://staging.example.com/a" \
  npx playwright test rendering-strategy.spec.ts
```

The suite exits non-zero on any failure, which gates CI on rendering
correctness.

### `lighthouserc.yml`

A starter Lighthouse CI configuration that asserts thresholds on the
rendering-related metrics from the chapter. LCP under 2.5 seconds, FCP
under 2 seconds, CLS under 0.1, TBT under 200 ms. The performance
category is at "warn" rather than "error" so it does not block
deployments on minor regressions, but the individual metric assertions
are hard errors.

Every assertion uses the median of the runs. Lighthouse CI's default is
"optimistic", the best value across runs, so a page that is slow two
times out of three would otherwise pass. Reports are written to
`./lhci-reports` (gitignored). The commonly copied
`target: temporary-public-storage` publishes each report, with page
screenshots, at a public URL, so only switch to it for pages that are
already public.

Edit the `url` list at the top with your staging URLs. Run with:

```bash
npm install -g @lhci/cli
lhci autorun
```

### `speculation-rules-validator.py`

Validates a Speculation Rules JSON configuration against the risky
patterns described in the chapter. It can either fetch the rules from
a live URL or read a local JSON file. For a URL, it collects every
source the browser would use and merges them: all
`<script type="speculationrules">` elements, and every JSON file named
in a `Speculation-Rules` response header (CDN features such as
Cloudflare's Speed Brain deliver rules this way). A source the browser
would ignore, such as invalid JSON or a header file that can't be
fetched, is listed separately, and the rest are still validated.

Patterns under a `not` clause are treated as exclusions, not targets. A
rule that prerenders `/*` except `/logout` is the recommended safe shape
and passes. `href_matches` values written as URLPattern objects
(`{"pathname": "/cart/*"}`) are checked like string patterns.

It flags:

- `eagerness: immediate` paired with broad `where` patterns, which
  produces high origin load.
- `eagerness: immediate` paired with selector matches. Document rules
  default to `conservative`, so this only happens when set explicitly,
  and it's rarely what you want for prerender at scale.
- An invalid `eagerness` value (anything other than `immediate`,
  `eager`, `moderate`, or `conservative`), which the browser ignores
  outright so the speculation silently never runs.
- Missing `eagerness`, which defaults to `immediate` for `urls` lists
  and may produce unintended speculative load.
- Prerender rules pointing at URL patterns that look like one-time
  action pages (`/checkout/`, `/confirm/`, `/cart/`, `/add-to-cart`,
  `/unsubscribe/`, `/logout/`, `/order/*/complete`, and similar,
  including their `?query=` forms). These should never be prerendered.
- Broad prerender rules with no exclusions at all (low severity), since
  any link to an action page that later appears on the page would be
  prerendered.
- Cross-origin URLs in rules without a corresponding
  `Supports-Loading-Mode: credentialed-prerender` consideration.

The script does not check `Sec-Purpose` handling in your application,
because that lives in server code the validator cannot see. Treat the
output as a starting list for review, not as a complete audit.

Usage:

```bash
# Validate the rules a live page uses (inline scripts and header files)
python speculation-rules-validator.py --url https://example.com/

# Validate a local JSON file
python speculation-rules-validator.py --file rules.json
```

The script exits 1 on any high-severity finding, so it can gate CI, and
exits 2 when no rules could be loaded.

### `example-speculation-rules.json`

A sample rules file that the validator can run against. Useful for
exercising the validator before you point it at production rules.

### `prerender-aware-analytics.example.js`

A small browser-side ES module that wraps the `document.prerendering` /
`prerenderingchange` pattern from the chapter. It exports a single
`onPageActive(callback)` helper that invokes the callback exactly once
per page load: immediately for a normal navigation, or after the
prerendered page is activated by the user. Drop it into your client
bundle and use it to gate analytics, conversion pixels, and A/B
variant assignment so speculative loads do not inflate metrics.

The immediate-vs-deferred behavior is locked in by
`prerender-aware-analytics.example.test.js` (run with `npm run test:unit`,
which uses the built-in `node --test` runner with a stubbed `document`
and needs no extra dependency; `npm test` runs the Playwright suite).

## Tests

After Setup, from this directory:

```bash
python3 -m pytest -q   # speculation-rules-validator.py
npm run test:unit      # prerender-aware-analytics.example.js
```

Or from the repo root: `make test-chapter-05-javascript-rendering` and
`make test-js-chapter-05-javascript-rendering`. The validator tests serve
pages, rule files and `Speculation-Rules` headers from a local HTTP
server, so they run offline.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.