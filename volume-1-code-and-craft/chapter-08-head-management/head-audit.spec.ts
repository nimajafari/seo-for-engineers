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
// Edit the PAGES_TO_AUDIT array below with your staging URLs, or set
// HEAD_AUDIT_PAGES to the path of a JSON file holding the same array:
//
//   HEAD_AUDIT_PAGES=pages.json npx playwright test head-audit.spec.ts
//
// The `shouldIndex` flag controls whether the URL is expected to be
// indexable; URLs marked false are expected to have noindex set at
// either the meta-tag or X-Robots-Tag header layer.
//
// Title and canonical are read from <head> only: an SVG <title> in the
// body is not the page title, and Google ignores canonicals in the
// body. Robots directives are parsed with the same rules as
// noindex-deployment-gate.js, so "max-image-preview:none" is not
// mistaken for noindex and <meta name="ROBOTS"> still counts.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';

import { hasNoindex } from './noindex-deployment-gate.js';

type AuditEntry = {
  url: string;
  type: string;
  shouldIndex: boolean;
  // Optional: if set, the canonical href must share this origin. Leave
  // unset on staging, where canonicals legitimately point at production.
  expectedCanonicalOrigin?: string;
};

// After the load event, wait for the network to go quiet, capped so
// analytics beacons and long-polling cannot hold every test for the
// full timeout, then a short settle (HEAD_AUDIT_SETTLE_MS, default
// 500) for tags that client-side scripts add after the last response.
const NETWORK_IDLE_CAP_MS = 5_000;
const SETTLE_MS = Number(process.env.HEAD_AUDIT_SETTLE_MS ?? 500);

const DEFAULT_PAGES: AuditEntry[] = [
  { url: 'https://staging.example.com/',                  type: 'home',    shouldIndex: true  },
  { url: 'https://staging.example.com/products/sample',   type: 'product', shouldIndex: true  },
  { url: 'https://staging.example.com/account/settings',  type: 'account', shouldIndex: false },
  { url: 'https://staging.example.com/search?q=boots',    type: 'search',  shouldIndex: false },
];

const PAGES_TO_AUDIT: AuditEntry[] = process.env.HEAD_AUDIT_PAGES
  ? JSON.parse(readFileSync(process.env.HEAD_AUDIT_PAGES, 'utf-8'))
  : DEFAULT_PAGES;

for (const entry of PAGES_TO_AUDIT) {
  const { url, type, shouldIndex, expectedCanonicalOrigin } = entry;

  test.describe(`<head> audit, ${type}: ${url}`, () => {
    // Captured per test in beforeEach. Some noindex deployments live
    // only in the X-Robots-Tag response header, so we keep it alongside
    // the rendered <head>.
    // Every X-Robots-Tag header, kept separate so a "googlebot:" prefix
    // in one does not bleed into the next.
    let xRobotsTag: string[] = [];

    test.beforeEach(async ({ page }) => {
      const response = await page.goto(url, { waitUntil: 'load' });
      await page
        .waitForLoadState('networkidle', { timeout: NETWORK_IDLE_CAP_MS })
        .catch(() => {});
      if (SETTLE_MS > 0) await page.waitForTimeout(SETTLE_MS);
      xRobotsTag = ((await response?.headersArray()) ?? [])
        .filter((h) => h.name.toLowerCase() === 'x-robots-tag')
        .map((h) => h.value);
    });

    // ── Title ──────────────────────────────────────────────────────────────

    test('contains exactly one title element with valid content', async ({ page }) => {
      const titles = page.locator('head > title');
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
      const canonicals = page.locator('head link[rel~="canonical" i]');
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
      // Every robots and googlebot tag counts, and the name is
      // case-insensitive, as it is for Google.
      const metaContents = await page
        .locator('meta[name="robots" i], meta[name="googlebot" i]')
        .evaluateAll((tags) => tags.map((t) => t.getAttribute('content') ?? ''));
      const metaContent = metaContents.join(' | ');

      // Combine both signals so a noindex set at either layer is detected.
      const isNoindex = xRobotsTag.some(hasNoindex) || metaContents.some(hasNoindex);

      if (shouldIndex) {
        expect(
          isNoindex,
          `expected ${url} to be indexable, but noindex was set ` +
            `(x-robots-tag="${xRobotsTag.join(' | ')}", meta="${metaContent}")`,
        ).toBe(false);
      } else {
        expect(
          isNoindex,
          `expected ${url} to be noindex, but neither layer set it ` +
            `(x-robots-tag="${xRobotsTag.join(' | ')}", meta="${metaContent}")`,
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

      const cardType = ((await twitterCard.getAttribute('content')) ?? '').trim();
      expect(['summary', 'summary_large_image', 'app', 'player']).toContain(cardType);

      // X falls back to og:title and og:description when the twitter:
      // tags are absent, so either one satisfies each requirement.
      for (const field of ['title', 'description']) {
        const count = await page
          .locator(`meta[name="twitter:${field}"], meta[property="og:${field}"]`)
          .count();
        expect(count, `expected twitter:${field} or og:${field}`).toBeGreaterThan(0);
      }
    });

    // ── Charset ────────────────────────────────────────────────────────────

    test('declares UTF-8 charset', async ({ page }) => {
      // <meta charset="utf-8"> or the older http-equiv form; both are valid.
      const declarations = await page
        .locator('meta[charset], meta[http-equiv="content-type" i]')
        .evaluateAll((tags) =>
          tags.map((t) =>
            t.getAttribute('charset') ??
            /charset\s*=\s*([^;\s]+)/i.exec(t.getAttribute('content') ?? '')?.[1] ??
            '',
          ),
        );
      expect(declarations, 'expected exactly one charset declaration').toHaveLength(1);
      expect(declarations[0].trim().toLowerCase()).toBe('utf-8');
    });

    // ── hreflang (non-blocking shape, hard once present) ───────────────────

    test('hreflang tags are consistent if present', async ({ page }) => {
      const hreflangs = page.locator('link[rel="alternate"][hreflang]');
      const count = await hreflangs.count();

      if (count === 0) return; // Not required on all pages.

      // SOFT: Google recommends, but does not require, an x-default.
      const xDefaults = await page.locator('link[rel="alternate"][hreflang="x-default" i]').count();
      if (xDefaults === 0) {
        console.warn(`[soft] ${url}: hreflang is used but there is no x-default`);
      }
      expect(xDefaults, 'expected at most one x-default').toBeLessThanOrEqual(1);

      // Every hreflang href must be absolute.
      for (let i = 0; i < count; i++) {
        const href = (await hreflangs.nth(i).getAttribute('href')) ?? '';
        expect(href).toMatch(/^https?:\/\//);
      }
    });
  });
}
