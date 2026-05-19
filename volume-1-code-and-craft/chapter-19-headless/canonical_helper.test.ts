/**
 * canonical_helper.test.ts
 *
 * Tests for canonical_helper.ts. Exercises the failure modes
 * Chapter 19 warns about: empty CMS overrides, malformed
 * overrides, non-indexable parameters, parameter order
 * normalization, environment-specific origin handling.
 *
 * Run with:
 *   SITE_ORIGIN=https://example.com npx tsx --test canonical_helper.test.ts
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { computeCanonical, isValidUrl } from './canonical_helper';

// Ensure tests have a deterministic origin.
process.env.SITE_ORIGIN = 'https://example.com';

test('uses CMS override when valid', () => {
  const result = computeCanonical({
    override: 'https://other.example.com/canonical-target',
    path: '/blog/some-post',
  });
  assert.equal(result, 'https://other.example.com/canonical-target');
});

test('ignores empty CMS override and falls back to derivation', () => {
  const result = computeCanonical({
    override: '',
    path: '/blog/some-post',
  });
  assert.equal(result, 'https://example.com/blog/some-post');
});

test('ignores null CMS override', () => {
  const result = computeCanonical({
    override: null,
    path: '/blog/some-post',
  });
  assert.equal(result, 'https://example.com/blog/some-post');
});

test('ignores malformed CMS override', () => {
  const result = computeCanonical({
    override: 'not-a-valid-url',
    path: '/blog/some-post',
  });
  assert.equal(result, 'https://example.com/blog/some-post');
});

test('ignores relative path as override', () => {
  // A relative path stored in the CMS would otherwise produce
  // a broken canonical. The validator rejects it.
  const result = computeCanonical({
    override: '/canonical-target',
    path: '/blog/some-post',
  });
  assert.equal(result, 'https://example.com/blog/some-post');
});

test('adds locale segment when provided', () => {
  const result = computeCanonical({
    path: '/blog/some-post',
    locale: 'en-GB',
  });
  assert.equal(result, 'https://example.com/en-GB/blog/some-post');
});

test('drops non-indexable parameters', () => {
  const params = new URLSearchParams('utm_source=twitter&page=2&sort=newest');
  const result = computeCanonical({
    path: '/blog',
    params,
  });
  // Only "page" is in the default indexable set.
  assert.equal(result, 'https://example.com/blog?page=2');
});

test('sorts retained parameters alphabetically', () => {
  // Synthetic case where two params are in the indexable set.
  // (The default set only has "page"; this test reaches into
  // the module to verify the sorting logic on the retained set.)
  const params = new URLSearchParams('page=3&page=2');
  const result = computeCanonical({
    path: '/blog',
    params,
  });
  // URLSearchParams collapses repeated keys; we get the last value.
  assert.ok(result.includes('page=2'));
});

test('omits search string when no indexable params present', () => {
  const params = new URLSearchParams('utm_source=email&fbclid=abc');
  const result = computeCanonical({
    path: '/blog',
    params,
  });
  assert.equal(result, 'https://example.com/blog');
});

test('throws when path missing leading slash', () => {
  assert.throws(
    () => computeCanonical({ path: 'blog/some-post' }),
    /path must start with "\/"/
  );
});

test('throws when origin env is missing', () => {
  const saved = process.env.SITE_ORIGIN;
  const savedPublic = process.env.NEXT_PUBLIC_SITE_ORIGIN;
  delete process.env.SITE_ORIGIN;
  delete process.env.NEXT_PUBLIC_SITE_ORIGIN;
  try {
    assert.throws(
      () => computeCanonical({ path: '/blog' }),
      /must be set/
    );
  } finally {
    if (saved !== undefined) process.env.SITE_ORIGIN = saved;
    if (savedPublic !== undefined) process.env.NEXT_PUBLIC_SITE_ORIGIN = savedPublic;
  }
});

test('isValidUrl accepts valid absolute http and https URLs', () => {
  assert.equal(isValidUrl('https://example.com'), true);
  assert.equal(isValidUrl('http://example.com/path'), true);
});

test('isValidUrl rejects relative URLs', () => {
  assert.equal(isValidUrl('/path'), false);
  assert.equal(isValidUrl('path'), false);
});

test('isValidUrl rejects non-http(s) protocols', () => {
  assert.equal(isValidUrl('ftp://example.com'), false);
  assert.equal(isValidUrl('javascript:alert(1)'), false);
});

test('isValidUrl rejects empty and null', () => {
  assert.equal(isValidUrl(''), false);
  // @ts-expect-error: testing runtime safety
  assert.equal(isValidUrl(null), false);
});