# SEO for Engineers

This repository is the operational complement to *SEO for Engineers* by
Bartosz Goralewicz. Every code block in the book that is worth running
in production has a tested, packaged version in this repository. The
chapter directories follow the book's structure; the code does the work
the chapters argue should be done.

## Status

**Volume 1, *Code and Craft*, is feature-complete.** All 19 chapter
directories are shipped under [`volume-1-code-and-craft/`](volume-1-code-and-craft/).

Volume 2, is in progress.

## What this repository is for

The book is about treating SEO as an emergent property of engineering
decisions. The repository is where those decisions become code. The
distinction matters because most published SEO material is one of two
things: prose without runnable artifacts, or runnable artifacts without
the reasoning behind them. This repository is the runnable half; the
book is the reasoning half. They are intended to be used together.

A reader who has worked through Volume 1 and adopted the artifacts in
this repository can expect to ship:

- A sitemap generator that produces conformant XML at any scale and
  that respects the 50,000-URL and 50 MB limits (Chapter 14).
- A `robots.txt` CI gate that catches the single most common
  catastrophic SEO regression before it ships (Chapter 15).
- A Googlebot verifier that handles spoofing correctly, not the
  user-agent string check most teams ship (Chapter 16).
- A faceted navigation classifier that decides per-URL whether to
  index, canonicalize, or `noindex`, with the centralization Chapter
  17 argues for.
- A log analysis pipeline (parse, verify, enrich, query) that turns
  raw CDN logs into actionable SEO observability (Chapter 18).
- A headless SEO audit tool, a CMS contract validator, and the
  responsibility matrix that names the cross-system ownership the
  chapter argues is required (Chapter 19).

Each of these is a real artifact, tested, with a smoke test script in
its chapter README. None is theoretical.

## Repository layout seo-for-engineers/
```text
├── README.md             (this file)
├── CHANGELOG.md          (versioned release notes, one per chapter)
├── CITATIONS.md          (primary sources cited across all chapters)
├── LICENSE               (MIT, applies uniformly across the repository)
├── Makefile              (top-level test orchestration, see below)
└── volume-1-code-and-craft/
├── README.md         (Volume 1 chapter index)
├── chapter-01-crawling/
├── chapter-02-rendering/
├── ...
└── chapter-19-headless/

Every chapter directory follows the same shape:chapter-NN-topic/
├── README.md             (chapter-specific guide, with usage examples)
├── requirements.txt      (or package.json for TypeScript/JavaScript)
├── <scripts>             (the chapter's runnable artifacts)
└── <tests>               (smoke tests and unit tests where applicable)

The chapter README is the entry point. Read it before running anything.
Every script has a `--help` flag.

## Running the tests

```bashTest everything across all chapters.
make test-allTest a single chapter.
make test CHAPTER=chapter-18-log-analysisLint and format checks.
make lint

The Makefile is documented in detail at [`Makefile`](Makefile). All
tests are designed to run in CI without external dependencies; tests
that hit live services (Search Console API, Google's IP range JSON,
sample CMS APIs) are gated behind environment variables and skipped
in their absence.

## Using this code in your own projects

The license is MIT, which means: use it, fork it, ship it, modify it,
embed it in commercial work. Attribution is appreciated but not
required. The book contains the reasoning; the repository contains the
code. If you ship something downstream that incorporates substantial
portions of these artifacts, a one-line credit to the book in your own
project's documentation is the kind of small thing that helps the work
reach more engineers.

A few of the artifacts here are particularly common in downstream
adoption:

- **`verify-googlebot.py`** from Chapter 16 is the canonical Googlebot
  verifier. Several teams have adopted it as their production tool. The
  IP-range caching and reverse DNS handling are production-tested.
- **`facet_classifier.py`** from Chapter 17 is the reference
  implementation of the `classify_request` pattern. Several teams have
  adapted it as the basis for their own classification logic.
- **`headless_seo_audit.py`** from Chapter 19 is increasingly used as a
  post-deploy CI gate.

If you adopt any of these into your own pipeline, the README in each
chapter directory has explicit guidance on customization.

## Volume 1 in one paragraph

The premise of Volume 1 is that the surfaces engineers build, URLs,
HTTP responses, JavaScript bundles, sitemaps, `robots.txt` files,
canonical tags, structured data, log pipelines, headless APIs, are the
surfaces search engines actually see. Every other discussion of SEO
operates one layer above the code; this volume operates at the layer
of the code itself. The 19 chapters move from the fundamentals of how
crawlers and indexers work, through the frontend surfaces (rendering,
Core Web Vitals, semantic HTML, head management, structured data,
internal linking, internationalization), into the backend disciplines
(URL design, HTTP fundamentals, sitemaps, `robots.txt`, crawl budget,
faceted navigation, log analysis), and end with the integrative topic
of headless architecture, which stresses every preceding discipline
simultaneously.

## Contributing

Errata, corrections, and improvements are welcome. Open an issue or a
pull request. For substantive changes (new scripts, API changes, new
chapters), file an issue first to discuss approach.

The repository is maintained alongside the book. If you find a code
issue that traces to ambiguous or incorrect prose in the manuscript,
say so in the issue. The repository and the book are co-equal sources
of truth; if they disagree, that is a bug in one or both.

## Volume 2

Volume 2, *Systems and Operations*, picks up where Volume 1 leaves
off. Where Volume 1 covers the surfaces engineers build, Volume 2
covers the systems that ship, operate, and monitor those surfaces, and
the engineering culture that determines whether SEO is a shared
discipline or a recurring source of incidents. Chapter directories for
Volume 2 will appear under `volume-2-systems-and-operations/` as they
are completed.
