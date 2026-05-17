// generate-product-alt.example.js
//
// Reference implementation of the programmatic alt-text generator
// described in Chapter 7 of SEO for Engineers, Volume 1. Produces a
// natural-language alt description from structured product data so
// large catalogs can ship indexable, descriptive image markup
// without manually-authored alt strings.
//
// Why this matters. CMS and e-commerce platforms frequently generate
// alt text automatically from page titles, producing values like
// "Product Image" or "Photo 1". These are functionally equivalent to
// empty alt from a crawler's perspective. A page with 50 product
// images and templated alt sends 50 useless signals to image search.
// Machine-generated alt from structured data, while imperfect, is
// substantially better.
//
// Usage:
//
//   import { generateProductAlt } from
//     './generate-product-alt.example.js';
//
//   const alt = generateProductAlt({
//     name: 'Nike Air Max',
//     color: 'Blue',
//     category: 'running shoes',
//     primaryAttribute: 'carbon fiber sole',
//   });
//   // -> "Blue running shoes with carbon fiber sole, Nike Air Max"
//
// Partial data is handled cleanly. Missing fields are skipped
// without producing double spaces or leading/trailing punctuation:
//
//   generateProductAlt({ category: 'shoes' });
//   // -> "shoes"
//
//   generateProductAlt({ name: 'Nike Air Max', category: 'shoes' });
//   // -> "shoes, Nike Air Max"
//
//   generateProductAlt({});
//   // -> ""
//
// In a React component:
//
//   <img
//     src={product.imageUrl}
//     alt={generateProductAlt(product)}
//     width={product.imageWidth}
//     height={product.imageHeight}
//   />
//
// This is a scaffold, not a final answer. Real implementations
// typically extend it with product variant attributes (size, finish),
// numeric specifications, and brand-specific phrasing.
//
// Reference: SEO for Engineers, Volume 1, Chapter 7.

/**
 * @typedef {object} Product
 * @property {string} [name]
 * @property {string} [color]
 * @property {string} [category]
 * @property {string} [primaryAttribute]
 */

/**
 * Generate alt text for a product image from structured data. Missing
 * fields are skipped; the output never has trailing punctuation or
 * doubled separators.
 *
 * @param {Product} product
 * @returns {string}
 */
export function generateProductAlt(product = {}) {
  const { name, color, category, primaryAttribute } = product;

  // Color and category form the leading descriptor, joined with a
  // single space only when both are present. Joining with .join(' ')
  // after filtering Boolean values avoids the double-space hazard of
  // pre-baking trailing spaces into each fragment.
  const descriptor = [color, category].filter(Boolean).join(' ');

  const clauses = [
    descriptor,
    primaryAttribute && `with ${primaryAttribute}`,
  ].filter(Boolean);

  let alt = clauses.join(' ');
  if (name) {
    alt = alt ? `${alt}, ${name}` : name;
  }
  return alt;
}
