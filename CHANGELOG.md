# Changelog

All notable corrections, clarifications, and updates to *SEO for Engineers*
are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), adapted for a
book's errata log.

## [Unreleased]

Nothing yet.

## [2.0.0] - 2026

**Volume 1, *Code and Craft*, is feature-complete.**

All 19 chapter directories under `volume-1-code-and-craft/` ship
production-grade repository materials matched to the chapter prose:
scripts, tests, reference implementations, SQL queries, citations,
and team document templates. The 2.0 cut marks the milestone where
the book and its repository are operationally interchangeable: any
code block in the manuscript that is worth running in production
has a tested, packaged version in this repository.

Total artifact count at 2.0:

- 19 chapter directories under `volume-1-code-and-craft/`
- 47 standalone scripts (Python, TypeScript, JavaScript, Bash)
- 12 SQL reference files for BigQuery and DuckDB analytics
- 9 test suites (pytest, Node test runner)
- 1 responsibility matrix template (Chapter 19)
- 1 top-level CITATIONS.md with primary sources for every chapter
- 1 LICENSE applying uniformly across all chapter materials

No content has been removed at 2.0. All previous 1.x release
entries are preserved below.

Volume 2, *Systems and Operations*, begins next.

## [1.18.0] - 2026

Added repository materials for Chapter 19, APIs, Headless
Architecture, and SEO. With this release, all 19 chapter
directories are shipped and Volume 1, *Code and Craft*, is
feature-complete.

- New: `volume-1-code-and-craft/chapter-19-headless/` directory
  with `canonical_helper.ts` (the productized `computeCanonical`
  helper from section 19.4, with tests), `product_schema.tsx`
  (the JSON-LD pattern from section 19.5 as a React component,
  with tests), `headless_seo_audit.py` (the Chapter 19
  diagnostics checklist as a runnable script), `cms_contract_validator.py`
  (schema-drift detection for headless CMS APIs), and
  `responsibility_matrix.md` (the section 19.3 matrix as a
  forkable team document), plus a `requirements.txt` and chapter
  README.
- Updated: `CITATIONS.md` with Chapter 19 primary sources,
  including Google's JavaScript SEO basics, soft 404
  documentation, URL Inspection tool, structured data
  introduction, Schema Markup Validator, Rich Results Test,
  `schema-dts`, and the Next.js `generateMetadata` and `notFound`
  documentation.
- Updated: `volume-1-code-and-craft/README.md`. All 19 chapters
  are now marked shipped. Volume 1 is feature-complete.

## [1.17.0] - 2026

Added repository materials for Chapter 18, Log File Analysis for
Backend Engineers.

## [1.16.0] - 2026

Added repository materials for Chapter 17, Faceted Navigation.

## [1.15.0] - 2026

Added repository materials for Chapter 16, Crawl Budget.

## [1.14.0] - 2026

Added repository materials for Chapter 15, robots.txt, The
Specification Engineers Should Actually Read.

## [1.13.0] - 2026

Added repository materials for Chapter 14, Sitemaps as a Backend
Responsibility.

## [1.12.0] - 2026

Added repository materials for Chapter 13, HTTP Fundamentals for SEO.

## [1.11.0] - 2026

Added repository materials for Chapter 12, URL Design as an
Engineering Discipline.

## [1.10.0] - 2026

Added repository materials for Chapter 11, Internationalization and
Multilingual SEO Engineering.

## [1.9.0] - 2026

Added repository materials for Chapter 10, Internal Linking as a
Graph Problem.

## [1.8.0] - 2026

Added repository materials for Chapter 9, Structured Data at Scale.

## [1.7.0] - 2026

Added repository materials for Chapter 8, Meta Tags, Canonical Tags,
and Head Management.

## [1.6.0] - 2026

Added repository materials for Chapter 7, Semantic HTML and
Information Architecture for Machines.

## [1.5.0] - 2026

Added repository materials for Chapter 6, Core Web Vitals as an
Engineering Discipline.

## [1.4.0] - 2026

Added repository materials for Chapter 5, JavaScript Rendering and
the Crawlability Challenge.

## [1.3.0] - 2026

Added repository materials for Chapter 4, Ranking Signals That
Engineering Controls.

## [1.2.0] - 2026

Added repository materials for Chapter 3, Indexing, Canonicalization,
and Duplicate Detection.

## [1.1.0] - 2026

Added repository materials for Chapter 2, The Rendering Pipeline.

## [1.0.0] - 2026

Initial release. Repository materials for Chapter 1, Crawling as a
Distributed System.