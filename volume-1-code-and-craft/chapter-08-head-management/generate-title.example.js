// generate-title.example.js
//
// Reference implementation of the title-template pattern described
// in Chapter 8 of SEO for Engineers, Volume 1. Generates per-page-
// type `<title>` strings from structured page data. Designed for
// sites with hundreds of thousands or millions of pages where
// hand-written titles are not feasible.
//
// The function returns the title verbatim. Pair it with the
// validation checks in generate-title.example.test.js to enforce
// the chapter's two title invariants:
//   1. Every page type produces a non-empty title.
//   2. Distinct content does not collapse to the same title.
//
// Usage:
//
//   import { generateTitle } from './generate-title.example.js';
//
//   generateTitle({
//     type: 'product',
//     productName: 'Merrell Moab 3 GTX',
//     category: "Women's Hiking Boots",
//   }, { brand: 'OutdoorGear', tagline: 'Built for the trail' });
//   // -> "Merrell Moab 3 GTX, Women's Hiking Boots | OutdoorGear"
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

/**
 * @typedef {object} SiteConfig
 * @property {string} brand
 * @property {string} [tagline]
 */

/**
 * @typedef {object} Page
 * @property {'product' | 'category' | 'article' | 'home' | string} type
 * @property {string} [productName]
 * @property {string} [category]
 * @property {string} [categoryName]
 * @property {number} [count]
 * @property {string} [headline]
 * @property {string} [h1]
 */

/**
 * Generate the <title> string for a page from structured data and
 * site config. Falls back to the page's <h1> + brand for unknown
 * page types so the default path still produces a non-empty title.
 *
 * @param {Page} page
 * @param {SiteConfig} site
 * @returns {string}
 */
/**
 * True when every value is a non-empty, non-whitespace string. Used to
 * guard each template branch: a missing field must not interpolate the
 * literal "undefined" into a title, which would satisfy the non-empty
 * invariant with garbage. Failing the guard falls through to the safe
 * h1/brand path instead.
 *
 * @param {...unknown} values
 * @returns {boolean}
 */
function allPresent(...values) {
  return values.every((v) => typeof v === 'string' && v.trim().length > 0);
}

export function generateTitle(page, site) {
  switch (page.type) {
    case 'product':
      if (allPresent(page.productName, page.category)) {
        return `${page.productName}, ${page.category} | ${site.brand}`;
      }
      break;

    case 'category':
      if (allPresent(page.categoryName)) {
        return page.count && page.count > 0
          ? `${page.categoryName}, ${page.count} Products | ${site.brand}`
          : `${page.categoryName} | ${site.brand}`;
      }
      break;

    case 'article':
      if (allPresent(page.headline)) {
        return `${page.headline} | ${site.brand}`;
      }
      break;

    case 'home':
      return site.tagline
        ? `${site.brand}, ${site.tagline}`
        : site.brand;
  }

  // The load-bearing fallback. Reached for unknown page types and for
  // known types whose required fields were missing. If the page has a
  // usable h1 we brand it; otherwise the brand alone is the floor, so
  // the title is never empty and never contains "undefined".
  return allPresent(page.h1)
    ? `${page.h1} | ${site.brand}`
    : site.brand;
}
