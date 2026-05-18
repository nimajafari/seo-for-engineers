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

## Reference snippets

### `schema-builder.example.ts`

A TypeScript builder module exporting `ProductSchemaBuilder` and
`BreadcrumbSchemaBuilder` plus the `SchemaBuilder<T>` interface.
Each builder owns its required-field validation, enumeration mapping,
and sanitization (full three-character escape: `<`, `>`, `&`), so the
rest of the application never assembles raw JSON-LD by hand. Builders
return `null` when required fields are missing, on the principle that
emitting no structured data is always better than emitting invalid
structured data.

Improvements over the chapter version:
- `description` is sanitized only when present, so the builder does
  not crash on undefined input.
- `mapAvailability` includes `discontinued -> Discontinued`, matching
  the chapter's Django helper and `structured-data-extractor.py`.

### `ci-validate-structured-data.example.js`

A CI gate script that fetches a list of URLs, extracts every
`<script type="application/ld+json">` block, validates each one
against per-type Ajv schemas, and applies a regression baseline that
asserts which `@type` values each URL template is expected to emit.
Designed to run as a blocking step in CI/CD; exits non-zero on JSON
syntax errors, schema-validation failures, or regressions.

Improvement over the chapter version: the `Offer.availability`
regex includes all ten Google-supported enum values (`InStock`,
`OutOfStock`, `OnlineOnly`, `InStoreOnly`, `PreOrder`, `PreSale`,
`BackOrder`, `SoldOut`, `Discontinued`, `LimitedAvailability`),
matching `structured-data-extractor.py`'s `VALID_AVAILABILITY`.

Install:

```bash
npm install jsdom ajv ajv-formats
```

Usage:

```bash
node ci-validate-structured-data.example.js \
  --base-url http://localhost:3000 \
  --url /products/sample-product \
  --url /blog/sample-article \
  --url /
```

### `examples/`

Four reference JSON-LD documents — complete, copy-pasteable markup
that satisfies Google's required-field requirements for each type.
Useful as starting points for new pages and as fixtures for test
suites that ingest known-good schema documents.

| File | Type | Notes |
| --- | --- | --- |
| `product.example.json` | `Product` | Includes nested `Offer`, `shippingDetails`, `hasMerchantReturnPolicy`, `aggregateRating`, and a `Review` array. Covers the full feature surface of Google's Merchant Listings rich-results requirements. |
| `article.example.json` | `Article` | Includes typed `author` with `sameAs` Knowledge-Graph anchors, `publisher` with logo, `datePublished` / `dateModified`, and `mainEntityOfPage`. |
| `local-business.example.json` | `Restaurant` (`LocalBusiness` subtype) | Includes `PostalAddress`, `GeoCoordinates`, weekday + weekend `openingHoursSpecification`, `servesCuisine`, `priceRange`. |
| `breadcrumb-list.example.json` | `BreadcrumbList` | Three-level navigation hierarchy with `ListItem` entries. |

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.