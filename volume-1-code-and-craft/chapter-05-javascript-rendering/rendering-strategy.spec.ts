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
// The no-JavaScript check runs in a context created with
// javaScriptEnabled: false (test.use). Playwright has no
// page.setJavaScriptEnabled(); that is a Puppeteer API.
//
// Usage:
//   npm install
//   npx playwright install chromium
//   npx playwright test rendering-strategy.spec.ts
//
//   # Or point it at other URLs without editing the file
//   SEO_TEST_URLS="https://staging.example.com/ https://staging.example.com/a" \
//     npx playwright test rendering-strategy.spec.ts
//
// Reference: SEO for Engineers, Volume 1, Chapter 5.

import { test, expect, Page } from '@playwright/test';

// Edit this list with the URLs you want to verify. Staging URLs are the
// expected target for CI use. SEO_TEST_URLS (whitespace- or
// comma-separated) overrides it, so CI can pass URLs per environment.
const DEFAULT_URLS: string[] = [
  'https://staging.example.com/',
  'https://staging.example.com/products/test-product',
];
const URLS_TO_TEST: string[] = process.env.SEO_TEST_URLS
  ? process.env.SEO_TEST_URLS.split(/[\s,]+/).filter(Boolean)
  : DEFAULT_URLS;

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
  canonicalHrefs: string[];
  robotsNoindex: boolean;
  structuredDataBlocks: number;
  invalidStructuredDataBlocks: number;
}

async function takeSnapshot(page: Page): Promise<SeoSnapshot> {
  const title = (await page.title()).trim();

  const h1 = await page.$('h1');
  const h1Text = h1 ? ((await h1.textContent()) ?? '').trim() : null;

  // rel is a token list and case-insensitive: match rel="Canonical" and
  // rel="canonical foo" too, and collect every one so duplicates fail.
  const canonicalHrefs = await page.$$eval(
    'link[rel~="canonical" i]',
    (links) => links.map((l) => (l.getAttribute('href') ?? '').trim())
  );

  // A noindex in the initial HTML stops Google before it renders, so
  // JavaScript that later removes it never gets the chance.
  const robotsNoindex = await page.$$eval(
    'meta[name="robots" i], meta[name="googlebot" i]',
    (metas) =>
      metas.some((m) => /\bnoindex\b|\bnone\b/i.test(m.getAttribute('content') ?? ''))
  );

  // Check every JSON-LD block, not just the first.
  const ldJsonTexts = await page.$$eval(
    'script[type="application/ld+json" i]',
    (scripts) => scripts.map((s) => (s.textContent ?? '').trim())
  );
  let invalidStructuredDataBlocks = 0;
  for (const text of ldJsonTexts) {
    try {
      JSON.parse(text);
    } catch {
      invalidStructuredDataBlocks += 1;
    }
  }

  return {
    // The final URL after redirects, so the canonical host comparison
    // uses the host that actually served the page.
    url: page.url(),
    title,
    h1Text,
    canonicalHrefs,
    robotsNoindex,
    structuredDataBlocks: ldJsonTexts.length,
    invalidStructuredDataBlocks,
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
    snapshot.robotsNoindex,
    `${label}: robots meta says noindex`
  ).toBe(false);

  expect(
    snapshot.canonicalHrefs.length,
    `${label}: expected exactly one <link rel="canonical">, found ` +
      `${snapshot.canonicalHrefs.length}`
  ).toBe(1);

  const canonicalHref = snapshot.canonicalHrefs[0];
  if (canonicalHref !== undefined) {
    // Canonical must be absolute.
    expect(
      /^https?:\/\//i.test(canonicalHref),
      `${label}: canonical href is not absolute (${canonicalHref})`
    ).toBe(true);

    // Canonical host should match the page host. Cross-host canonicals
    // are legitimate for syndicated content but are worth flagging in CI.
    if (/^https?:\/\//i.test(canonicalHref)) {
      const canonicalHost = new URL(canonicalHref).host;
      const pageHost = new URL(snapshot.url).host;
      expect(
        canonicalHost,
        `${label}: canonical host (${canonicalHost}) does not match ` +
          `page host (${pageHost})`
      ).toBe(pageHost);
    }
  }

  expect(
    snapshot.structuredDataBlocks,
    `${label}: no application/ld+json script found`
  ).toBeGreaterThan(0);
  expect(
    snapshot.invalidStructuredDataBlocks,
    `${label}: ${snapshot.invalidStructuredDataBlocks} JSON-LD block(s) ` +
      `did not parse as valid JSON`
  ).toBe(0);
}

for (const url of URLS_TO_TEST) {
  test.describe(`SEO rendering for ${url}`, () => {
    test.describe('initial HTML response (no JS)', () => {
      // A fresh context with JavaScript off approximates wave one.
      test.use({ javaScriptEnabled: false });

      test('critical content is present in the initial HTML response', async ({
        page,
      }) => {
        await page.goto(url, { waitUntil: 'domcontentloaded' });
        const snapshot = await takeSnapshot(page);
        assertSnapshot(snapshot, 'initial response (no JS)');
      });
    });

    test('critical content is present in the rendered DOM', async ({
      page,
    }) => {
      await page.goto(url, { waitUntil: 'networkidle' });
      const snapshot = await takeSnapshot(page);
      assertSnapshot(snapshot, 'rendered DOM (with JS)');
    });
  });
}
