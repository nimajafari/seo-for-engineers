/**
 * product_schema.test.tsx
 *
 * Tests for the buildProductJsonLd function. Exercises the
 * conditional-inclusion behavior the chapter argues for: brand
 * and aggregateRating are emitted only when data is present, not
 * with null or zero.
 *
 * Run with:
 *   npx tsx --test product_schema.test.tsx
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildProductJsonLd, type Product } from './product_schema';

const baseProduct: Product = {
  handle: 'example-widget',
  displayName: 'Example Widget',
  description: 'A widget that exemplifies.',
  images: [
    { url: 'https://cdn.example.com/widget-1.jpg' },
    { url: 'https://cdn.example.com/widget-2.jpg' },
  ],
  sku: 'WIDGET-001',
  price: { amount: 29.99, currencyCode: 'USD' },
  availableForSale: true,
};

const ORIGIN = 'https://www.example.com';

test('emits required Product fields', () => {
  const jsonLd = buildProductJsonLd(baseProduct, ORIGIN);
  assert.equal(jsonLd['@context'], 'https://schema.org');
  assert.equal(jsonLd['@type'], 'Product');
  assert.equal(jsonLd.name, 'Example Widget');
  assert.equal(jsonLd.description, 'A widget that exemplifies.');
  assert.deepEqual(jsonLd.sku, 'WIDGET-001');
});

test('emits offers with InStock when available', () => {
  const jsonLd = buildProductJsonLd(baseProduct, ORIGIN);
  const offers = jsonLd.offers as Record<string, unknown>;
  assert.equal(offers['@type'], 'Offer');
  assert.equal(offers.availability, 'https://schema.org/InStock');
  assert.equal(offers.url, 'https://www.example.com/products/example-widget');
});

test('emits offers with OutOfStock when unavailable', () => {
  const jsonLd = buildProductJsonLd(
    { ...baseProduct, availableForSale: false },
    ORIGIN,
  );
  const offers = jsonLd.offers as Record<string, unknown>;
  assert.equal(offers.availability, 'https://schema.org/OutOfStock');
});

test('omits brand when not present', () => {
  const jsonLd = buildProductJsonLd(baseProduct, ORIGIN);
  assert.equal(jsonLd.brand, undefined);
});

test('emits brand when present', () => {
  const jsonLd = buildProductJsonLd(
    { ...baseProduct, brand: { name: 'Acme' } },
    ORIGIN,
  );
  assert.deepEqual(jsonLd.brand, { '@type': 'Brand', name: 'Acme' });
});

test('omits aggregateRating when reviewStats is null', () => {
  const jsonLd = buildProductJsonLd(baseProduct, ORIGIN);
  assert.equal(jsonLd.aggregateRating, undefined);
});

test('omits aggregateRating when count is zero', () => {
  // Schema.org requires at least one review for aggregateRating
  // to be valid. Emitting it with count=0 is a violation that
  // Rich Results Test will flag.
  const jsonLd = buildProductJsonLd(
    {
      ...baseProduct,
      reviewStats: { average: 4.5, count: 0 },
    },
    ORIGIN,
  );
  assert.equal(jsonLd.aggregateRating, undefined);
});

test('emits aggregateRating when reviewStats is present and non-zero', () => {
  const jsonLd = buildProductJsonLd(
    {
      ...baseProduct,
      reviewStats: { average: 4.5, count: 23 },
    },
    ORIGIN,
  );
  assert.deepEqual(jsonLd.aggregateRating, {
    '@type': 'AggregateRating',
    ratingValue: 4.5,
    reviewCount: 23,
  });
});

test('serializes to valid JSON', () => {
  const jsonLd = buildProductJsonLd(
    {
      ...baseProduct,
      brand: { name: 'Acme' },
      reviewStats: { average: 4.5, count: 23 },
    },
    ORIGIN,
  );
  const serialized = JSON.stringify(jsonLd);
  // Parsing the serialized form should round-trip.
  const parsed = JSON.parse(serialized);
  assert.equal(parsed['@type'], 'Product');
  assert.equal(parsed.brand['@type'], 'Brand');
  assert.equal(parsed.aggregateRating.reviewCount, 23);
});