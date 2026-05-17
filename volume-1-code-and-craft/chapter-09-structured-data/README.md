# Chapter 9, Structured Data at Scale

This directory contains the diagnostic scripts referenced in Chapter 9
of *SEO for Engineers, Volume 1*. The scripts cover the two checks
engineers most often need beyond Google's Rich Results Test, namely
validating JSON-LD against Google's required-field requirements at
scale, and checking that the values declared in JSON-LD actually match
what is visible on the rendered page.

## Scripts

### `structured-data-extractor.py`

A Python script that fetches a URL (or a list of URLs) and extracts
all JSON-LD blocks from the rendered HTML, parses each block, and
validates it against a registry of per-type rules.

The registry encodes Google's required-field requirements for the
schema types Chapter 9 identifies as highest value:

- `Product` (with nested `Offer`, `AggregateRating`, `Review`)
- `Article`, `NewsArticle`, `BlogPosting`
- `BreadcrumbList`
- `Recipe`
- `Event`
- `LocalBusiness` and its supported subtypes
- `Organization`
- `VideoObject`

It also flags the use of deprecated types (`FAQPage`, `HowTo`,
`SpecialAnnouncement`, `LearningVideo`, `CourseInfo`, `ClaimReview`,
`EstimatedSalary`, `VehicleListing`, `BookActions`, `PracticeProblem`)
which produce dead-code findings, matching Failure Mode 7 from the
chapter.

The script reports findings in three severity buckets.

**High severity.** Invalid JSON syntax, missing required Schema.org or
Google fields for a declared type, deprecated rich-result types,
and unsanitized HTML-significant characters in user-generated string
values (the XSS pattern from Failure Mode 8).

**Medium severity.** Missing strongly recommended fields, missing
`sameAs` on `Organization` or `Person` (which weakens entity
resolution), and `availability` values outside the Schema.org
enumeration.

**Low severity.** Missing optional but valuable fields (e.g.,
`gtin13` on `Product`).

Usage:
Audit a single URL
python structured-data-extractor.py --url https://example.com/
Audit a list of URLs
python structured-data-extractor.py --urls-file urls.txt
JSON output to a file
python structured-data-extractor.py --url https://example.com/ --output report.json

Install:
pip install -r requirements.txt

### `schema-consistency-checker.js`

A Playwright-based script that addresses Failure Mode 4, the
content-markup mismatch. It loads a URL, extracts the JSON-LD, and
runs a configurable set of consistency checks comparing values
declared in the JSON-LD against values visible in the rendered DOM.

The default checks cover the most common product-page mismatches.

- `Product.name` in JSON-LD must appear in the page `<h1>`.
- `Offer.price` numeric value must appear somewhere in the visible
  text of the page (formatted with the declared `priceCurrency`).
- `Offer.availability` must be consistent with whatever stock-status
  text is visible on the page (the script accepts a configurable
  pattern map between Schema.org availability URLs and text snippets).
- `BreadcrumbList` `name` values must each appear in a visible
  `<nav>` landmark.

The checks are written to fail closed. A mismatch is reported as a
finding, not silently swallowed. Where the page rendering involves
multiple price formats, decimal separators, or currency placements,
the script tries common variants before reporting a mismatch.

Usage:
node schema-consistency-checker.js https://example.com/products/widget
Multiple URLs
node schema-consistency-checker.js --urls https://example.com/products/widget https://example.com/products/another
Run only specific checks
node schema-consistency-checker.js https://example.com/products/widget --checks name,price

Install:

```bash
npm install
npx playwright install chromium
```

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.