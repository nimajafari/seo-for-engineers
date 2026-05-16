// rendering-strategy.spec.ts
//
// Playwright test suite that verifies the SEO-critical content of a
// page in both the initial HTTP response (no JavaScript) and the
// rendered DOM (full JavaScript execution).
//
// The first check approximates Googlebot's wave-one processing. The
// second approximates the wave-two render. A page that fails the
// first check but passes the second is dependent on JavaScript
// rendering for indexing, which means it sits behind the rendering
// queue and risks delayed or partial indexing.
//
// Usage:
//   npm install
//   npx playwright install chromium
//   npx playwright test rendering-strategy.spec.ts
//
// Reference: SEO for Engineers, Volume 1, Chapter 5.

import { test, expect, Page } from '@playwright/test';

// Edit this list with the URLs you want to verify. Staging URLs are the
// expected target for CI use.
const URLS_TO_TEST: string[] = [
  'https://staging.example.com/',
  'https://staging.example.com/products/test-product',
];

// Title strings that indicate the framework's static fallback rather
// than a real page title. Extend this list as needed.
const FALLBACK_TITLES = new Set<string>([
  '',
  'My Application',
  'My App',
  'React App',
  'Next.js',
  'Vue App',
  'Loading...',
]);

interface SeoSnapshot {
  url: string;
  title: string;
  h1Text: string | null;
  canonicalHref: string | null;
  hasStructuredData: boolean;
  structuredDataIsValid: boolean;
  structuredDataType: string | null;
}

async function takeSnapshot(page: Page, url: string): Promise<SeoSnapshot> {
  const title = await page.title();

  const h1 = await page.$('h1');
  const h1Text = h1 ? ((await h1.textContent()) ?? '').trim() : null;

  const canonical = await page.$('link[rel="canonical"]');
  const canonicalHref = canonical
    ? await canonical.getAttribute('href')
    : null;

  const ldJsonElement = await page.$('script[type="application/ld+json"]');
  const ldJsonText = ldJsonElement
    ? ((await ldJsonElement.textContent()) ?? '').trim()
    : null;

  let structuredDataIsValid = false;
  let structuredDataType: string | null = null;
  if (ldJsonText) {
    try {
      const parsed = JSON.parse(ldJsonText);
      structuredDataIsValid = true;
      if (parsed && typeof parsed === 'object') {
        structuredDataType =
          (parsed['@type'] as string | undefined) ?? null;
      }
    } catch {
      structuredDataIsValid = false;
    }
  }

  return {
    url,
    title,
    h1Text,
    canonicalHref,
    hasStructuredData: Boolean(ldJsonText),
    structuredDataIsValid,
    structuredDataType,
  };
}

function assertSnapshot(snapshot: SeoSnapshot, label: string): void {
  expect(snapshot.title, `${label}: <title> is empty`).not.toBe('');
  expect(
    FALLBACK_TITLES.has(snapshot.title),
    `${label}: <title> is the framework fallback "${snapshot.title}"`
  ).toBe(false);

  expect(snapshot.h1Text, `${label}: <h1> is missing`).not.toBeNull();
  expect(snapshot.h1Text, `${label}: <h1> is empty`).not.toBe('');

  expect(
    snapshot.canonicalHref,
    `${label}: <link rel="canonical"> is missing`
  ).not.toBeNull();

  // Canonical must be absolute.
  if (snapshot.canonicalHref) {
    expect(
      snapshot.canonicalHref.startsWith('http://') ||
        snapshot.canonicalHref.startsWith('https://'),
      `${label}: canonical href is not absolute (${snapshot.canonicalHref})`
    ).toBe(true);

    // Canonical host should match the page host. Cross-host canonicals
    // are legitimate for syndicated content but are worth flagging in CI.
    try {
      const canonicalHost = new URL(snapshot.canonicalHref).host;
      const pageHost = new URL(snapshot.url).host;
      expect(
        canonicalHost,
        `${label}: canonical host (${canonicalHost}) does not match ` +
          `page host (${pageHost})`
      ).toBe(pageHost);
    } catch {
      // Already failed the "absolute" assertion above.
    }
  }

  expect(
    snapshot.hasStructuredData,
    `${label}: no application/ld+json script found`
  ).toBe(true);

  if (snapshot.hasStructuredData) {
    expect(
      snapshot.structuredDataIsValid,
      `${label}: JSON-LD did not parse as valid JSON`
    ).toBe(true);
  }
}

for (const url of URLS_TO_TEST) {
  test.describe(`SEO rendering for ${url}`, () => {
    test('critical content is present in the initial HTML response', async ({
      page,
    }) => {
      await page.setJavaScriptEnabled(false);
      await page.goto(url, { waitUntil: 'domcontentloaded' });
      const snapshot = await takeSnapshot(page, url);
      assertSnapshot(snapshot, 'initial response (no JS)');
    });

    test('critical content is present in the rendered DOM', async ({
      page,
    }) => {
      await page.goto(url, { waitUntil: 'networkidle' });
      const snapshot = await takeSnapshot(page, url);
      assertSnapshot(snapshot, 'rendered DOM (with JS)');
    });
  });
}