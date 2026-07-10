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
page. It runs two checks against every URL. First, with JavaScript
disabled, which approximates the initial HTTP response that Googlebot
processes in wave one. Second, with JavaScript enabled and the page
allowed to reach `networkidle`, which approximates what Googlebot's
wave-two render produces.

Each check asserts on:

- `<h1>` is present and not the framework fallback.
- `<title>` is present and not the static framework placeholder.
- `<link rel="canonical">` exists and points to an absolute URL.
- A JSON-LD `<script>` block exists and parses as valid JSON.
- No `<link rel="canonical">` to a different host than the page.

This is the working version of the test example in the chapter,
extended with the practical assertions you actually want in CI.

To use it, edit the `URLS_TO_TEST` array at the top of the file with
the URLs you want to verify (typically staging), then, after Setup, run:

```bash
npx playwright test rendering-strategy.spec.ts
```

The suite exits non-zero on any failure, which gates CI on rendering
correctness.

### `lighthouserc.yml`

A starter Lighthouse CI configuration that asserts thresholds on the
rendering-related metrics from the chapter. LCP under 2.5 seconds, FCP
under 2 seconds, CLS under 0.1. The performance category is at "warn"
rather than "error" so it does not block deployments on minor
regressions, but the individual metric assertions are hard errors.

Edit the `url` list at the top with your staging URLs. Run with:

```bash
npm install -g @lhci/cli
lhci autorun
```

### `speculation-rules-validator.py`

Validates a Speculation Rules JSON configuration against the risky
patterns described in the chapter. It can either fetch the rules from
a live URL (the browser unions every `<script type="speculationrules">`
element on the page, so the validator parses and merges all of them)
or read a local JSON file.

It flags:

- `eagerness: immediate` paired with broad `where` patterns, which
  produces high origin load.
- `eagerness: immediate` paired with selector matches, which is the
  default and rarely what you want for prerender at scale.
- An invalid `eagerness` value (anything other than `immediate`,
  `eager`, `moderate`, or `conservative`), which the browser ignores
  outright so the speculation silently never runs.
- Missing `eagerness`, which defaults to `immediate` for `urls` lists
  and may produce unintended speculative load.
- Prerender rules pointing at URL patterns that look like one-time
  action pages (`/checkout/`, `/confirm/`, `/cart/`, `/add-to-cart`,
  `/unsubscribe/`, `/logout/`, `/order/*/complete`, and similar,
  including their `?query=` forms). These should never be prerendered.
- Cross-origin URLs in rules without a corresponding
  `Supports-Loading-Mode: credentialed-prerender` consideration.

The script does not check `Sec-Purpose` handling in your application,
because that lives in server code the validator cannot see. Treat the
output as a starting list for review, not as a complete audit.

Usage:
Validate rules embedded in a live page
python speculation-rules-validator.py --url https://example.com/
Validate a local JSON file
python speculation-rules-validator.py --file rules.json

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

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.