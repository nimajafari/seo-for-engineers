# Chapter 7, Semantic HTML and Information Architecture for Machines

This directory contains the diagnostic scripts referenced in Chapter 7
of *SEO for Engineers, Volume 1*. The scripts audit pages for the
semantic HTML patterns the chapter argues matter for indexing quality,
content extraction, and anchor signal interpretation.

## Scripts

### `semantic-html-auditor.py`

A Python audit that fetches a URL (or a list of URLs) and checks each
page for the semantic HTML signals that affect indexing.

The audit reports findings in three severity buckets.

**High severity.** Missing `<h1>`, multiple `<h1>` elements at the page
level, missing `<main>` element, multiple visible `<main>` elements,
`<a>` elements with no `href`, anchor elements that produce no text
signal at all (no text, no `aria-label`, no `alt` on child images, no
visually hidden text).

**Medium severity.** Skipped heading levels (h2 followed by h4
without an intervening h3), images with no `alt` attribute, images
with generic template-level alt text (`Image`, `Photo`, `Picture`,
`Product Image`, and similar), `<button>` and `<a>` elements that
render only an icon without an accessible name.

**Low severity.** Missing `<header>`, missing `<footer>`, missing
top-level `<nav>`, headings inside `<aside>` that may pollute the
document outline.

The script does not try to be a full WCAG audit. It focuses on the
patterns Chapter 7 identifies as having the highest SEO impact.

Usage:
Audit a single URL
python semantic-html-auditor.py --url https://example.com/
Audit a list of URLs (one per line)
python semantic-html-auditor.py --urls-file urls.txt
JSON output to a file
python semantic-html-auditor.py --url https://example.com/ --output report.json

Install:
pip install -r requirements.txt

### `heading-hierarchy-validator.js`

A Playwright-based validator that loads a URL in headless Chromium and
validates the heading outline against the rules from Chapter 7.

It checks for multiple `<h1>` elements, skipped heading levels, and
headings inside structurally inappropriate parents (specifically,
inside `<aside>`, inside `<nav>`, and inside common UI component
roots like elements with `role="dialog"`, `role="menu"`, or class
names that match common card and modal patterns).

The Playwright-based check matters here in a way it does not for the
Python script. The validator runs against the rendered DOM, not the
raw HTML response, so it catches headings injected by JavaScript at
hydration time, which the Python auditor would miss.

Usage:
node heading-hierarchy-validator.js https://example.com/
Multiple URLs
node heading-hierarchy-validator.js --urls https://example.com/ https://example.com/products/widget

Install:

```bash
npm install
npx playwright install chromium
```

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.