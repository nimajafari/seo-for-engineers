/**
 * canonical_helper.ts
 *
 * Productized version of the computeCanonical helper from
 * Chapter 19 section 19.4. In a headless system the canonical URL
 * must be computed in one place, deterministically, from the five
 * inputs the chapter names: CMS override, path, locale, request
 * search params, and origin (read from the environment so preview
 * deploys do not emit production canonicals).
 *
 * The companion test file canonical_helper.test.ts exercises the
 * failure modes the chapter warns about.
 */

/**
 * Parameters the canonical helper accepts.
 *
 * - `override`: the CMS-supplied canonical URL, if any. Honored
 *   only when it parses as an absolute http/https URL. Empty
 *   strings, null, relative paths, and malformed values fall back
 *   to the derived form.
 * - `path`: the page's path on the site, starting with "/". Required.
 * - `locale`: optional locale segment to prepend (e.g., "en-GB").
 * - `params`: the request's search params. Only members of
 *   `indexableParams` are retained on the canonical; everything
 *   else is dropped.
 * - `indexableParams`: the set of param names that are part of the
 *   canonical identity. Defaults to `DEFAULT_INDEXABLE_PARAMS`.
 */
export interface CanonicalInputs {
  override?: string | null;
  path: string;
  locale?: string;
  params?: URLSearchParams;
  indexableParams?: Set<string>;
}

/**
 * Default set of query parameters that should be preserved on a
 * canonical URL. Pagination is the canonical example; sort, view,
 * and tracking parameters belong to the "dropped" set, per
 * Chapter 17's facet-tier classification.
 */
export const DEFAULT_INDEXABLE_PARAMS: ReadonlySet<string> = new Set([
  'page',
]);

/**
 * Strict URL validator. Accepts only absolute http/https URLs.
 * Rejects relative paths, javascript:, mailto:, ftp:, empty strings,
 * and null. Exposed because validating CMS-supplied URLs is useful
 * outside the canonical helper (sitemap generation, redirect
 * handling).
 */
export function isValidUrl(value: unknown): boolean {
  if (typeof value !== 'string' || value.length === 0) {
    return false;
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function readOrigin(): string {
  const origin = process.env.SITE_ORIGIN
    ?? process.env.NEXT_PUBLIC_SITE_ORIGIN;
  if (!origin) {
    throw new Error(
      'SITE_ORIGIN (or NEXT_PUBLIC_SITE_ORIGIN) must be set so the '
      + 'canonical helper can build absolute URLs.',
    );
  }
  return origin.replace(/\/$/, '');
}

/**
 * Compute the canonical URL for a page.
 *
 * Resolution order:
 *   1. If `override` is a valid absolute http/https URL, use it.
 *   2. Otherwise, build from origin + optional locale + path,
 *      retaining only `indexableParams` from `params`, sorted
 *      alphabetically by key.
 *
 * Throws when `path` does not start with "/" or when no origin
 * environment variable is set.
 */
export function computeCanonical(input: CanonicalInputs): string {
  if (!input.path.startsWith('/')) {
    throw new Error('path must start with "/", got: ' + input.path);
  }

  if (isValidUrl(input.override)) {
    return input.override as string;
  }

  const origin = readOrigin();
  const locale = input.locale ? `/${input.locale}` : '';
  const indexable = input.indexableParams ?? DEFAULT_INDEXABLE_PARAMS;

  const retained: [string, string][] = [];
  if (input.params) {
    const seen = new Set<string>();
    for (const [name, value] of input.params) {
      if (!indexable.has(name) || seen.has(name)) {
        continue;
      }
      // URLSearchParams iterates in insertion order; for repeated
      // keys, the last value wins to match the test fixture's
      // expectation that page=3&page=2 collapses to page=2.
      const last = input.params.getAll(name).at(-1);
      if (last !== undefined && last.length > 0) {
        retained.push([name, last]);
        seen.add(name);
      }
    }
  }
  retained.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));

  const search = retained.length > 0
    ? '?' + retained.map(([k, v]) =>
        `${encodeURIComponent(k)}=${encodeURIComponent(v)}`,
      ).join('&')
    : '';

  return `${origin}${locale}${input.path}${search}`;
}
