// head-audit.spec.ts
//
// Comprehensive rendered-DOM <head> audit, designed to run as part
// of a pre-deployment E2E suite. The Python head-audit.py in this
// same directory inspects the raw HTTP response; this spec inspects
// the rendered DOM after JavaScript has executed, so it catches
// head elements injected by client-side libraries that the HTTP
// auditor would miss.
//
// Assertions are split into one test() per concern so a failure
// reports precisely which element is wrong, rather than masking
// later checks behind the first failed expect.
//
// Two classes of check:
//   - HARD assertions fail the build (correctness: counts, presence,
//     absolute URLs, indexation posture).
//   - SOFT checks (SEO guidelines such as title/description length)
//     emit a console.warn instead of failing, mirroring how hreflang
//     is treated as non-blocking. Truncation in the SERP is advice,
//     not a deploy-blocking defect.
//
// Usage:
//   npx playwright test head-audit.spec.ts
//
// Edit the PAGES_TO_AUDIT array below with your staging URLs. The
// `shouldIndex` flag controls whether the URL is expected to be
// indexable; URLs marked false are expected to have noindex set at
// either the meta-tag or X-Robots-Tag header layer.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { expect, test } from '@playwright/test';

type AuditEntry = {
  url: string;
  type: string;
  shouldIndex: boolean;
  // Optional: if set, the canonical href must share this origin. Leave
  // unset on staging, where canonicals legitimately point at production.
  expectedCanonicalOrigin?: string;
};

const PAGES_TO_AUDIT: AuditEntry[] = [
  { url: 'https://staging.example.com/',                  type: 'home',    shouldIndex: true  },
  { url: 'https://staging.example.com/products/sample',   type: 'product', shouldIndex: true  },
  { url: 'https://staging.example.com/account/settings',  type: 'account', shouldIndex: false },
  { url: 'https://staging.example.com/search?q=boots',    type: 'search',  shouldIndex: false },
];

for (const entry of PAGES_TO_AUDIT) {
  const { url, type, shouldIndex, expectedCanonicalOrigin } = entry;

  test.describe(`<head> audit, ${type}: ${url}`, () => {
    // Captured per test in beforeEach. Some noindex deployments live
    // only in the X-Robots-Tag response header, so we keep it alongside
    // the rendered <head>.
    let xRobotsTag = '';

    test.beforeEach(async ({ page }) => {
      const response = await page.goto(url, { waitUntil: 'networkidle' });
      xRobotsTag = response?.headers()['x-robots-tag'] ?? '';
    });

    // ── Title ──────────────────────────────────────────────────────────────

    test('contains exactly one title element with valid content', async ({ page }) => {
      const titles = page.locator('title');
      await expect(titles).toHaveCount(1);

      const titleText = ((await titles.textContent()) ?? '').trim();
      expect(titleText.length, 'expected non-empty <title>').toBeGreaterThan(0);
      expect(titleText, 'expected non-placeholder <title>').not.toBe('Untitled');

      // SOFT: titles over ~60 chars are commonly truncated in the SERP.
      if (titleText.length > 60) {
        console.warn(`[soft] ${url}: <title> is ${titleText.length} chars (>60 may be truncated)`);
      }
    });

    // ── Canonical ──────────────────────────────────────────────────────────

    test('contains exactly one absolute, clean canonical URL', async ({ page }) => {
      const canonicals = page.locator('link[rel="canonical"]');
      await expect(canonicals).toHaveCount(1);

      const href = (await canonicals.getAttribute('href')) ?? '';
      expect(href, 'canonical must be absolute').toMatch(/^https?:\/\//);
      expect(href, 'canonical must not contain a query string').not.toContain('?');
      expect(href, 'canonical must not contain a fragment').not.toContain('#');

      // Same-origin is only enforced when explicitly opted in, since on
      // staging the canonical typically points at the production origin.
      if (expectedCanonicalOrigin) {
        expect(new URL(href).origin).toBe(expectedCanonicalOrigin);
      }
    });

    // ── Meta description ───────────────────────────────────────────────────

    test('contains at most one meta description with valid content', async ({ page }) => {
      const descriptions = page.locator('meta[name="description"]');
      const count = await descriptions.count();

      // Duplicate meta descriptions are a common CMS bug.
      expect(count, 'expected at most one meta description').toBeLessThanOrEqual(1);

      if (count === 1) {
        const content = ((await descriptions.getAttribute('content')) ?? '').trim();
        expect(content.length, 'expected non-empty meta description').toBeGreaterThan(0);

        // SOFT: 50–160 chars is the conventional sweet spot.
        if (content.length < 50 || content.length > 160) {
          console.warn(`[soft] ${url}: meta description is ${content.length} chars (outside 50–160)`);
        }
      }
    });

    // ── Robots / indexation posture ────────────────────────────────────────

    test('matches the expected indexation state', async ({ page }) => {
      const robotsMeta = page.locator('meta[name="robots"]');
      const metaContent =
        (await robotsMeta.count()) > 0 ? (await robotsMeta.first().getAttribute('content')) ?? '' : '';

      // Combine both signals so a noindex set at either layer is detected.
      const headerNoindex = xRobotsTag.toLowerCase().includes('noindex');
      const metaNoindex = metaContent.toLowerCase().includes('noindex');
      const isNoindex = headerNoindex || metaNoindex;

      if (shouldIndex) {
        expect(
          isNoindex,
          `expected ${url} to be indexable, but noindex was set ` +
            `(x-robots-tag="${xRobotsTag}", meta="${metaContent}")`,
        ).toBe(false);
      } else {
        expect(
          isNoindex,
          `expected ${url} to be noindex, but neither layer set it ` +
            `(x-robots-tag="${xRobotsTag}", meta="${metaContent}")`,
        ).toBe(true);
      }
    });

    // ── Viewport ───────────────────────────────────────────────────────────

    test('contains a viewport meta tag', async ({ page }) => {
      const viewport = page.locator('meta[name="viewport"]');
      await expect(viewport).toHaveCount(1);

      const content = (await viewport.getAttribute('content')) ?? '';
      expect(content).toContain('width=device-width');
    });

    // ── Open Graph ─────────────────────────────────────────────────────────

    test('contains required Open Graph metadata', async ({ page }) => {
      const ogTitle = page.locator('meta[property="og:title"]');
      await expect(ogTitle).toHaveCount(1);
      expect(((await ogTitle.getAttribute('content')) ?? '').trim().length).toBeGreaterThan(0);

      const ogDescription = page.locator('meta[property="og:description"]');
      await expect(ogDescription).toHaveCount(1);
      expect(((await ogDescription.getAttribute('content')) ?? '').trim().length).toBeGreaterThan(0);

      // og:url and og:image must be absolute.
      const ogUrl = page.locator('meta[property="og:url"]');
      await expect(ogUrl).toHaveCount(1);
      expect((await ogUrl.getAttribute('content')) ?? '').toMatch(/^https?:\/\//);

      const ogImage = page.locator('meta[property="og:image"]');
      await expect(ogImage).toHaveCount(1);
      expect((await ogImage.getAttribute('content')) ?? '').toMatch(/^https?:\/\//);

      const ogType = page.locator('meta[property="og:type"]');
      await expect(ogType).toHaveCount(1);
    });

    // ── Twitter / X Card ───────────────────────────────────────────────────

    test('contains required Twitter card metadata', async ({ page }) => {
      const twitterCard = page.locator('meta[name="twitter:card"]');
      await expect(twitterCard).toHaveCount(1);

      const cardType = (await twitterCard.getAttribute('content')) ?? '';
      expect(['summary', 'summary_large_image', 'app', 'player']).toContain(cardType);

      await expect(page.locator('meta[name="twitter:title"]')).toHaveCount(1);
      await expect(page.locator('meta[name="twitter:description"]')).toHaveCount(1);
    });

    // ── Charset ────────────────────────────────────────────────────────────

    test('declares UTF-8 charset', async ({ page }) => {
      const charset = page.locator('meta[charset]');
      await expect(charset).toHaveCount(1);

      const charsetValue = (await charset.getAttribute('charset')) ?? '';
      expect(charsetValue.toLowerCase()).toBe('utf-8');
    });

    // ── hreflang (non-blocking shape, hard once present) ───────────────────

    test('hreflang tags are consistent if present', async ({ page }) => {
      const hreflangs = page.locator('link[rel="alternate"][hreflang]');
      const count = await hreflangs.count();

      if (count === 0) return; // Not required on all pages.

      // x-default must be present when hreflang is used.
      await expect(page.locator('link[rel="alternate"][hreflang="x-default"]')).toHaveCount(1);

      // Every hreflang href must be absolute.
      for (let i = 0; i < count; i++) {
        const href = (await hreflangs.nth(i).getAttribute('href')) ?? '';
        expect(href).toMatch(/^https?:\/\//);
      }
    });
  });
}
