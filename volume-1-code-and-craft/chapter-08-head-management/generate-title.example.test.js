// generate-title.example.test.js
//
// Tests for generate-title.example.js. Uses Node's built-in test
// runner (node:test), available in Node 18+, so this file ships
// with no extra test-framework dependency.
//
// Run:
//   node --test generate-title.example.test.js
//
// The two invariants the chapter argues for, and that this file
// enforces:
//   1. Every page type produces a non-empty title.
//   2. Distinct content does not collapse to the same title.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import { generateTitle } from './generate-title.example.js';

const SITE = { brand: 'OutdoorGear', tagline: 'Built for the trail' };

describe('generateTitle', () => {
  it('produces unique titles for products in the same category', () => {
    const products = [
      { type: 'product', productName: 'Merrell Moab 3 GTX', category: "Women's Hiking Boots" },
      { type: 'product', productName: 'Salomon X Ultra 4',   category: "Women's Hiking Boots" },
      { type: 'product', productName: 'Hoka Speedgoat 5',    category: "Women's Hiking Boots" },
    ];
    const titles = products.map((p) => generateTitle(p, SITE));
    const unique = new Set(titles);
    assert.equal(unique.size, titles.length);
  });

  it('never produces an empty title across all page types', () => {
    const pages = [
      { type: 'product',  productName: 'Sample',     category: 'Boots' },
      { type: 'category', categoryName: 'Boots',     count: 42 },
      { type: 'category', categoryName: 'Boots',     count: 0 },
      { type: 'article',  headline: 'How to lace boots' },
      { type: 'home' },
      { type: 'unknown',  h1: 'Catch-all heading' },
    ];
    for (const page of pages) {
      const title = generateTitle(page, SITE);
      assert.ok(
        title.trim().length > 0,
        `empty title for ${JSON.stringify(page)}`,
      );
    }
  });

  it('avoids double-branding the title', () => {
    const title = generateTitle(
      { type: 'product', productName: 'Sample', category: 'Boots' },
      SITE,
    );
    // The brand should appear exactly once.
    const brandHits = title.split(SITE.brand).length - 1;
    assert.equal(brandHits, 1, `brand "${SITE.brand}" appears ${brandHits}x in "${title}"`);
  });

  it('falls back to brand alone when home has no tagline', () => {
    const title = generateTitle({ type: 'home' }, { brand: 'OutdoorGear' });
    assert.equal(title, 'OutdoorGear');
  });

  it('falls back to brand alone for unknown types without h1', () => {
    const title = generateTitle({ type: 'whatever' }, SITE);
    assert.equal(title, SITE.brand);
  });
});
