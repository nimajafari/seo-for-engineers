// head-audit.spec.ts
//
// Comprehensive rendered-DOM <head> audit, designed to run as part
// of a pre-deployment E2E suite. The Python head-audit.py in this
// same directory inspects the raw HTTP response; this spec inspects
// the rendered DOM after JavaScript has executed, so it catches
// head elements injected by client-side libraries that the HTTP
// auditor would miss.
//
// What it checks per URL:
//   - Exactly one <title> element with non-empty, non-placeholder text.
//   - Exactly one <link rel="canonical"> with an absolute URL.
//   - <meta name="robots"> presence/absence matches the page's
//     `shouldIndex` flag.
//   - og:title and og:image present (og:image with an absolute URL).
//
// Usage:
//   npx playwright test head-audit.spec.ts
//
// Edit the PAGES_TO_AUDIT array below with your staging URLs. The
// `shouldIndex` flag controls whether the URL is expected to be
// indexable; URLs marked false are expected to have noindex set.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { expect, test } from '@playwright/test';

type AuditEntry = {
  url: string;
  type: string;
  shouldIndex: boolean;
};

const PAGES_TO_AUDIT: AuditEntry[] = [
  { url: 'https://staging.example.com/',                  type: 'home',    shouldIndex: true  },
  { url: 'https://staging.example.com/products/sample',   type: 'product', shouldIndex: true  },
  { url: 'https://staging.example.com/account/settings',  type: 'account', shouldIndex: false },
  { url: 'https://staging.example.com/search?q=boots',    type: 'search',  shouldIndex: false },
];

for (const { url, type, shouldIndex } of PAGES_TO_AUDIT) {
  test.describe(`<head> audit, ${type}: ${url}`, () => {
    test('passes head correctness assertions', async ({ page }) => {
      const response = await page.goto(url, { waitUntil: 'networkidle' });

      // Capture both the response header (some noindex deployments
      // live only in X-Robots-Tag) and the rendered <head>.
      const xRobotsTag = response?.headers()['x-robots-tag'] ?? '';

      const headData = await page.evaluate(() => {
        const get = (selector: string, attr = 'content') =>
          document.querySelector(selector)?.getAttribute(attr) ?? null;

        return {
          title: document.title,
          canonical: get('link[rel="canonical"]', 'href'),
          robots: get('meta[name="robots"]'),
          ogTitle: get('meta[property="og:title"]'),
          ogImage: get('meta[property="og:image"]'),
          description: get('meta[name="description"]'),
          titleCount: document.querySelectorAll('title').length,
          canonicalCount: document.querySelectorAll('link[rel="canonical"]').length,
        };
      });

      // Exactly one <title>, non-empty, not a placeholder.
      expect(headData.titleCount, 'expected exactly one <title>').toBe(1);
      expect(headData.title.trim().length, 'expected non-empty <title>').toBeGreaterThan(0);
      expect(headData.title, 'expected non-placeholder <title>').not.toBe('Untitled');

      // Exactly one absolute canonical.
      expect(
        headData.canonicalCount,
        'expected exactly one <link rel="canonical">',
      ).toBe(1);
      expect(headData.canonical).toMatch(/^https?:\/\//);

      // Indexing posture matches the page's intent. Combine the
      // meta-tag and header signals so a noindex set at either layer
      // is detected.
      const headerNoindex = xRobotsTag.toLowerCase().includes('noindex');
      const metaNoindex = (headData.robots ?? '').toLowerCase().includes('noindex');
      const isNoindex = headerNoindex || metaNoindex;

      if (shouldIndex) {
        expect(
          isNoindex,
          `expected ${url} to be indexable, but noindex was set ` +
            `(x-robots-tag="${xRobotsTag}", meta="${headData.robots ?? ''}")`,
        ).toBe(false);
      } else {
        expect(
          isNoindex,
          `expected ${url} to be noindex, but neither layer set it`,
        ).toBe(true);
      }

      // OG presence checks. og:title is required for predictable
      // social rendering; og:image must be absolute.
      expect(headData.ogTitle, 'expected og:title').not.toBeNull();
      expect(headData.ogImage, 'expected og:image').not.toBeNull();
      expect(headData.ogImage).toMatch(/^https?:\/\//);
    });
  });
}
