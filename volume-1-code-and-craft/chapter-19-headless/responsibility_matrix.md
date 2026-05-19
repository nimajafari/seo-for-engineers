# SEO Responsibility Matrix, Headless Architecture

A template for the responsibility matrix from *SEO for Engineers,
Volume 1, Chapter 19*. The chapter argues that this matrix is
"the single most important artifact of a well-run headless SEO
practice."

Fork this file into your own engineering documentation. Replace
the *Owner* column with the actual team or named individual on
your team. Review the matrix whenever the architecture changes.

## How to use

For every SEO-relevant signal, four questions must have explicit
answers.

1. **Data source.** Which system stores the authoritative value
   for this signal? Usually the CMS, sometimes the rendering
   layer (derived values), occasionally the CDN (cache
   directives, geo-routing).
2. **Emitted by.** Which system writes the signal into the
   response the crawler sees? In headless this is almost always
   the rendering layer, sometimes the CDN.
3. **Common failure point.** The specific failure mode the
   chapter names for this signal. Use this as the diagnostic
   starting point during incidents.
4. **Owner.** The team or named individual on the hook when the
   signal breaks. This must be a name, not "engineering". If no
   one is named, no one will fix it.

Two additional columns are recommended for production use.

5. **Validation.** The script, test suite, or monitoring check
   that asserts this signal is correct. Without this column, you
   have a contract but no enforcement.
6. **Recovery time objective.** How quickly the owner commits to
   restoring the signal after an incident. SEO incidents have
   compounding cost over time; a `noindex` left in production for
   12 hours costs more than 12x what it costs in 1 hour.

## The matrix

| Signal | Data source | Emitted by | Common failure point | Owner | Validation | RTO |
| --- | --- | --- | --- | --- | --- | --- |
| Canonical URL | CMS override or derived | Rendering layer | Empty CMS field, wrong fallback logic | _team_ | `canonical_helper.test.ts`, `headless_seo_audit.py` | 1 hour |
| Title tag | CMS | Rendering layer | Missing fallback, CSR overwrite timing | _team_ | `headless_seo_audit.py`, `cms_contract_validator.py` | 1 hour |
| Meta description | CMS | Rendering layer | Same as title | _team_ | `headless_seo_audit.py`, `cms_contract_validator.py` | 4 hours |
| HTTP status (`200`/`404`/`410`) | CMS state | Rendering layer | Deleted records returning `200` (soft `404`) | _team_ | `headless_seo_audit.py --expect-404` | 1 hour |
| Redirects | CMS redirect table | Rendering layer or CDN | Redirect table not synced to frontend | _team_ | `headless_seo_audit.py --expect-301` | 4 hours |
| Sitemap URLs | Rendering layer (route walk) | Rendering layer | Sitemap from stale build | _team_ | `sitemap-auditor.py` (Chapter 14) | 24 hours |
| `robots.txt` | Frontend or CDN | Rendering layer or CDN | Environment-specific files missing | _team_ | `robots-ci-check.py` (Chapter 15) | 30 min |
| Structured data | CMS content | Rendering layer | JSON-LD references fields not rendered | _team_ | `product_schema.test.tsx`, `headless_seo_audit.py` | 24 hours |
| hreflang | CMS (locale model) | Rendering layer | Missing return tags, broken graph | _team_ | manual review | 1 week |
| Cache headers | CDN or framework | CDN | `Cache-Control` conflicts between layers | _team_ | manual verification | 1 hour |
| `X-Robots-Tag` (preview environments) | Environment config | Rendering layer or CDN | Stripped by CDN normalization | _team_ | `headless_seo_audit.py` against preview | 30 min |

## Common edits

When you fork this for your team, you will typically:

- **Add rows** for site-specific signals (custom schema types you
  emit, internal taxonomy fields that drive canonical structure,
  faceted navigation patterns from Chapter 17).
- **Replace `_team_`** with actual team names. *"SEO is everyone's
  job"* is the failure pattern; *"frontend-platform owns canonical
  computation, content-platform owns CMS schema"* is the pattern
  that works.
- **Sharpen RTOs** based on the business cost of each signal. A
  product retailer that depends on rich results in the SERP will
  have tighter RTOs on structured data than a blog.
- **Link the Validation column** to the actual file paths in your
  monorepo or CI pipeline, not the chapter-19 directory in this
  repo. The chapter-19 scripts are starting points, not the
  finished tool.

## Review cadence

The matrix is a living artifact. Review it:

- **Quarterly**, as a standing engineering review. Add rows for
  new signals, retire rows for signals no longer in scope.
- **On every architectural change**, before merging. A new CMS
  field, a new rendering strategy, a new CDN behavior is a row in
  the matrix; if it isn't, ownership is implicit and ownership
  that is implicit is ownership that will fail.
- **After every SEO incident**, as part of the post-mortem. If
  the incident traced to an unnamed signal, add the row. If the
  incident traced to an unclear owner, sharpen the owner column.

The matrix is the operational artifact of the chapter's central
argument: headless SEO works when the seams between systems are
named explicitly. Names belong on a page. This page is the page.