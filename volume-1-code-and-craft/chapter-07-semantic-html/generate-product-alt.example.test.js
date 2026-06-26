// generate-product-alt.example.test.js
//
// Tests for generate-product-alt.example.js. Uses Node's built-in test
// runner (node:test), available in Node 18+, so this file ships with no
// extra test-framework dependency.
//
// Run:
//   node --test generate-product-alt.example.test.js
//
// The invariants the chapter argues for, and that this file enforces:
//   1. Partial data is handled cleanly: missing fields are skipped with
//      no doubled separators and no leading/trailing punctuation.
//   2. The documented input -> output examples hold exactly.
//   3. Fully absent data yields an empty string (a decorative-image
//      signal), never the literal "undefined".
//
// Reference: SEO for Engineers, Volume 1, Chapter 7.

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { generateProductAlt } from './generate-product-alt.example.js';

describe('generateProductAlt', () => {
  it('matches the documented examples exactly', () => {
    const cases = [
      [{}, ''],
      [{ category: 'shoes' }, 'shoes'],
      [{ name: 'Nike Air Max', category: 'shoes' }, 'shoes, Nike Air Max'],
      [
        {
          name: 'Nike Air Max',
          color: 'Blue',
          category: 'running shoes',
          primaryAttribute: 'carbon fiber sole',
        },
        'Blue running shoes with carbon fiber sole, Nike Air Max',
      ],
    ];
    for (const [product, expected] of cases) {
      assert.equal(
        generateProductAlt(product),
        expected,
        `for ${JSON.stringify(product)}`,
      );
    }
  });

  it('never emits doubled spaces or stray separators for partial data', () => {
    const partials = [
      { color: 'Blue' },
      { primaryAttribute: 'carbon sole' },
      { name: 'Nike Air Max' },
      { color: 'Blue', name: 'Nike Air Max' },
      { category: 'running shoes', primaryAttribute: 'carbon sole' },
    ];
    for (const product of partials) {
      const alt = generateProductAlt(product);
      assert.doesNotMatch(alt, /\s{2,}/, `doubled space in "${alt}"`);
      assert.doesNotMatch(alt, /^[\s,]|[\s,]$/, `stray separator in "${alt}"`);
      assert.doesNotMatch(
        alt,
        /undefined|null/,
        `placeholder leaked into "${alt}"`,
      );
    }
  });

  it('returns an empty string for fully absent data', () => {
    // Empty alt is the correct decorative-image signal; it must never
    // be the string "undefined" from interpolating missing fields.
    assert.equal(generateProductAlt(), '');
    assert.equal(generateProductAlt({}), '');
  });

  it('appends the product name only when a descriptor exists', () => {
    // Name alone -> name; name with a descriptor -> "descriptor, name".
    assert.equal(generateProductAlt({ name: 'Nike Air Max' }), 'Nike Air Max');
    assert.equal(
      generateProductAlt({ category: 'shoes', name: 'Nike Air Max' }),
      'shoes, Nike Air Max',
    );
  });
});
