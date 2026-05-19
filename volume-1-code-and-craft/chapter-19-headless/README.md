# Chapter 19, APIs, Headless Architecture, and SEO

This directory contains the diagnostic tools, reference
implementations, and team-document templates referenced in
Chapter 19 of *SEO for Engineers, Volume 1*. The artifacts here
implement the chapter's central argument: in a headless
architecture, SEO is an emergent property of three systems
cooperating, and the path to reliability is naming the
responsibilities, contracts, and failure modes at the seams.

Five artifacts cover the chapter's full stack. The audit script
and contract validator are the diagnostic core, runnable against
any live origin or CMS endpoint. The canonical helper and product
schema component are reference implementations ready to drop into
a Next.js or similar React-based stack. The responsibility matrix
is the team document the chapter argues every headless practice
should maintain.

## Artifacts

### `canonical_helper.ts`

The productized version of the `computeCanonical` helper from
Chapter 19 section 19.4. The chapter argues that canonical URL
computation in a headless system must be centralized and
deterministic; this file is the reference implementation.

The module exports:

- `computeCanonical(input: CanonicalInputs)`, the main entry point.
  Takes the CMS override (if any), the path, the locale, and the
  request's search params, and returns the canonical URL.
- `CanonicalInputs`, the input type. Use this as the parameter
  type for callers.
- `isValidUrl(value)`, a strict URL validator. Exposed because
  validating CMS-supplied URLs is useful in other places (sitemap
  generation, redirect handling).
- `DEFAULT_INDEXABLE_PARAMS`, the default set of query parameter
  names that survive into the canonical. Override per-call via
  `CanonicalInputs.indexableParams`.

The implementation handles the five inputs the chapter names: CMS
override, path, locale, query parameters, and origin
(environment-configurable so preview deploys do not emit
production canonicals). The origin is read from `SITE_ORIGIN`,
with `NEXT_PUBLIC_SITE_ORIGIN` as the Next.js-style fallback. The
helper throws if neither is set, so a misconfigured preview deploy
fails loudly instead of emitting wrong canonicals.

The accompanying test file `canonical_helper.test.ts` exercises
the failure modes the chapter warns about: empty CMS overrides,
malformed CMS overrides, non-indexable parameters, parameter
order normalization, and environment-specific origin handling.

Usage in a Next.js page:

```typescript
import { computeCanonical } from '@/lib/seo/canonical_helper';

export async function generateMetadata({ params, searchParams }) {
  const post = await getPost(params.slug);
  if (!post) return { title: 'Not found' };

  const canonical = computeCanonical({
    override: post.seo?.canonicalOverride,
    path: `/blog/${post.slug}`,
    locale: post.locale,
    params: new URLSearchParams(searchParams),
  });

  return {
    title: post.seoTitle ?? post.title,
    alternates: { canonical },
  };
}
```

Run the tests with any TypeScript test runner. The file uses
Node's built-in `node:test`, which has no extra dependencies:

```bash
SITE_ORIGIN=https://example.com npx tsx --test canonical_helper.test.ts
```

### `product_schema.tsx`

The reference implementation of the `ProductSchema` React
component from Chapter 19 section 19.5. The chapter argues that
the JSON-LD on a page must be computed from the same data object
as the visible body, never re-fetched in a separate component.
This file is that pattern.

The component:

- Accepts a `Product` type that matches the Schema.org `Product`
  fields the file emits.
- Conditionally includes optional fields (`brand`, `aggregateRating`,
  `review`) rather than emitting them with `null` or empty strings,
  which is the schema-correct behavior.
- Uses `dangerouslySetInnerHTML` to emit raw JSON, which is the
  current recommended pattern for JSON-LD in React Server
  Components (React's default JSX escaping breaks JSON syntax).

This file is a reference template, not a runnable artifact on its
own. Copy it into your own components directory and adapt the
`Product` type to match your CMS schema. The test file
`product_schema.test.tsx` validates that the rendered JSON parses
as valid JSON and that the optional-field behavior works as
described.

### `headless_seo_audit.py`

The Chapter 19 diagnostics checklist as a runnable script. Given
a URL, the script fetches it with a configurable user agent and
asserts the SEO properties the chapter requires:

- HTTP status is `200` for content URLs, `404` for known-missing
  URLs (passed via `--expect-404`), `301` for known-moved URLs
  (passed via `--expect-301`).
- `X-Robots-Tag` header is absent for indexable URLs, contains
  `noindex` for non-indexable ones.
- Response body is non-empty (not a CSR-only shell).
- `<title>` tag is present and non-empty.
- `<meta name="description">` is present.
- `<link rel="canonical">` is present and points at a valid
  absolute URL.
- At least one JSON-LD `<script>` block is present.
- All JSON-LD blocks parse as valid JSON.
- The `og:title`, `og:description`, and `og:image` meta tags are
  present.

The script reports each assertion individually, with the URL, the
expected value, the observed value, and pass/fail. It exits 0
when all assertions pass and 1 otherwise, so it slots cleanly
into CI.

Usage:

```bash
# Audit a single URL
python headless_seo_audit.py https://www.example.com/products/widget

# Audit with a specific crawler user agent
python headless_seo_audit.py \
  --user-agent "Mozilla/5.0 (compatible; Googlebot/2.1)" \
  https://www.example.com/products/widget

# Audit a batch from stdin, one URL per line
cat urls.txt | python headless_seo_audit.py --batch

# Assert a URL returns 404
python headless_seo_audit.py --expect-404 https://www.example.com/deleted-post

# Output JSON for machine parsing
python headless_seo_audit.py --json https://www.example.com/products/widget
```

The script depends only on `requests` and `beautifulsoup4`, both
in `requirements.txt`. Run against your staging origin before
every production deploy, and against production on a schedule.

### `cms_contract_validator.py`

The contract validator from Chapter 19 section 19.5. Asserts that
the CMS API response for a given record contains all required
SEO fields, that they have the expected types, and that locale
coverage is complete. Catches the schema-drift failure mode the
chapter names: a CMS field gets renamed, becomes nullable, or
changes type, and the frontend silently breaks.

The validator works against any JSON response. You define the
contract as a Python dict mapping field paths to expected types
and constraints; the validator walks the contract and reports
violations.

Out of the box, the script ships with a default contract that
matches the chapter's recommended minimum SEO field set:

- `slug` (string, non-empty)
- `title` (string, non-empty)
- `publishedAt` (string, ISO 8601 datetime)
- `updatedAt` (string, ISO 8601 datetime)
- `status` (string, one of `published`, `draft`, `archived`)
- `seo.metaTitle` (string, may be null with a fallback)
- `seo.metaDescription` (string, may be null with a fallback)
- `seo.canonicalOverride` (string, may be null, must be a valid URL if set)
- `seo.noindex` (boolean)
- `seo.ogImage.url` (string, valid URL, may be absent)

Usage:

```bash
# Validate a single record from a REST endpoint
python cms_contract_validator.py \
  --url https://api.cms.example.com/posts/hello-world

# Validate a GraphQL response
python cms_contract_validator.py \
  --graphql https://api.cms.example.com/graphql \
  --query @query.gql \
  --variables '{"slug": "hello-world"}'

# Use a custom contract
python cms_contract_validator.py \
  --contract custom_contract.json \
  --url https://api.cms.example.com/posts/hello-world

# Batch mode: validate a list of record IDs
python cms_contract_validator.py \
  --url 'https://api.cms.example.com/posts/{id}' \
  --batch ids.txt
```

The contract is itself a Python data structure or a JSON file,
making it easy to extend with your own custom fields, locale
requirements, or product-specific constraints.

### `responsibility_matrix.md`

The responsibility matrix from Chapter 19 section 19.3, as a
forkable team document. The matrix lists every SEO-relevant
signal, names the data source, the system responsible for
emitting it, and the common failure point.

The chapter argues this matrix is "the single most important
artifact of a well-run headless SEO practice." This file is the
template; fork it into your own engineering documentation, name
the actual owners on your team, and review it whenever the
architecture changes.

The shipped version is the chapter's matrix plus three columns
the chapter implies but does not enumerate:

- **Owner.** The team or named individual on the hook when the
  signal breaks. Fill this in for your organization.
- **Validation.** Which artifact in this directory or in earlier
  chapter directories validates the signal in CI or production.
- **Recovery time objective.** How quickly the team commits to
  restoring the signal after an incident.

## Wiring into CI

The pipeline shape Chapter 19 argues for is three gates: contract
validation against the CMS, audit against the staging origin, and
audit against the production origin after deploy.

**Pre-deploy contract validation:**

```yaml
- name: Validate CMS contract
  run: |
    cd volume-1-code-and-craft/chapter-19-headless
    pip install -r requirements.txt
    python cms_contract_validator.py \
      --graphql ${{ secrets.CMS_GRAPHQL_URL }} \
      --query @../../../queries/page-by-slug.gql \
      --batch ../../../test/canonical-records.txt
```

**Post-deploy staging audit:**

```yaml
- name: Audit staging deploy
  run: |
    cd volume-1-code-and-craft/chapter-19-headless
    cat test/representative-urls.txt \
      | python headless_seo_audit.py --batch --base-url https://staging.example.com
```

**Post-deploy production audit:**

```yaml
- name: Audit production
  run: |
    cd volume-1-code-and-craft/chapter-19-headless
    cat test/representative-urls.txt \
      | python headless_seo_audit.py --batch --base-url https://www.example.com
```

Combined, these implement the chapter's argument that headless
SEO correctness is checked at every system boundary: at the CMS,
at the rendering layer's staging output, and at the production
output that crawlers actually see.

## Primary sources

The scripts and the chapter both reference the same primary
sources. See the top-level [`CITATIONS.md`](../../CITATIONS.md)
for the full list.
