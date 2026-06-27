// lcp-diagnostic.js
//
// Playwright-based LCP diagnostic. Loads a URL in headless Chromium,
// captures the LCP entry and navigation timing entry, computes the
// four-part decomposition described in Chapter 6 (TTFB, Resource Load
// Delay, Resource Load Duration, Element Render Delay), and emits a
// structured JSON report.
//
// Usage:
//   node lcp-diagnostic.js https://example.com/
//   node lcp-diagnostic.js --urls https://example.com/ https://example.com/products
//   node lcp-diagnostic.js --urls-file urls.txt
//   node lcp-diagnostic.js --form-factor mobile https://example.com/
//
// The four-part values are approximations computed from
// PerformanceObserver entries. They match what web-vitals/attribution
// reports in production. For text LCP elements, the resource sub-parts
// are zero and the rest flows into elementRenderDelay.
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import process from 'node:process';

const MOBILE_VIEWPORT = { width: 412, height: 915 };
const DESKTOP_VIEWPORT = { width: 1280, height: 800 };

const MOBILE_UA =
  'Mozilla/5.0 (Linux; Android 10; Pixel 5) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36';

function parseArgs(argv) {
  const args = { urls: [], formFactor: 'desktop', urlsFile: null };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--form-factor') {
      args.formFactor = tokens[++i];
    } else if (t === '--urls') {
      while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
        args.urls.push(tokens[++i]);
      }
    } else if (t === '--urls-file') {
      args.urlsFile = tokens[++i];
    } else if (t.startsWith('http')) {
      args.urls.push(t);
    }
  }
  if (args.urlsFile) {
    const lines = readFileSync(args.urlsFile, 'utf-8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('#')) {
        args.urls.push(trimmed);
      }
    }
  }
  return args;
}

function rate(lcpMs) {
  if (lcpMs <= 2500) return 'good';
  if (lcpMs <= 4000) return 'needs-improvement';
  return 'poor';
}

async function diagnoseOne(url, formFactor, browser) {
  const context = await browser.newContext({
    viewport: formFactor === 'mobile' ? MOBILE_VIEWPORT : DESKTOP_VIEWPORT,
    userAgent: formFactor === 'mobile' ? MOBILE_UA : undefined,
    deviceScaleFactor: formFactor === 'mobile' ? 2 : 1,
    isMobile: formFactor === 'mobile',
  });
  const page = await context.newPage();

  try {
    await page.goto(url, { waitUntil: 'load', timeout: 30_000 });
    // Wait briefly so late-loading LCP candidates settle.
    await page.waitForTimeout(2_000);

    const data = await page.evaluate(() => {
      const lcpEntries =
        performance.getEntriesByType('largest-contentful-paint');
      const lcpEntry = lcpEntries[lcpEntries.length - 1];
      if (!lcpEntry) {
        return { error: 'no_lcp_entry' };
      }

      const navEntry = performance.getEntriesByType('navigation')[0];
      // activationStart > 0 for prerender-activated navigations.
      const activationStart = navEntry?.activationStart || 0;
      const ttfb = Math.max(
        0,
        (navEntry?.responseStart || 0) - activationStart
      );

      // Find the resource entry that matches the LCP URL.
      let resourceEntry = null;
      if (lcpEntry.url) {
        const resources = performance.getEntriesByType('resource');
        resourceEntry = resources.find((r) => r.name === lcpEntry.url);
      }

      let resourceLoadDelay = 0;
      let resourceLoadDuration = 0;
      let elementRenderDelay = 0;

      if (resourceEntry) {
        const start = resourceEntry.startTime - activationStart;
        const end = resourceEntry.responseEnd - activationStart;
        resourceLoadDelay = Math.max(0, start - ttfb);
        resourceLoadDuration = Math.max(0, end - start);
        elementRenderDelay = Math.max(
          0,
          lcpEntry.startTime - activationStart - end
        );
      } else {
        // Text LCP. No separate resource fetch.
        elementRenderDelay = Math.max(
          0,
          lcpEntry.startTime - activationStart - ttfb
        );
      }

      const el = lcpEntry.element;
      const elementInfo = el
        ? {
            tag: el.tagName?.toLowerCase() || null,
            id: el.id || null,
            className:
              typeof el.className === 'string' ? el.className : null,
          }
        : null;

      return {
        lcp: Math.round(lcpEntry.startTime - activationStart),
        lcpUrl: lcpEntry.url || null,
        element: elementInfo,
        subParts: {
          ttfb: Math.round(ttfb),
          resourceLoadDelay: Math.round(resourceLoadDelay),
          resourceLoadDuration: Math.round(resourceLoadDuration),
          elementRenderDelay: Math.round(elementRenderDelay),
        },
        wasPrerenderActivation: activationStart > 0,
      };
    });

    if (data.error) {
      return { url, error: data.error };
    }

    return {
      url,
      formFactor,
      ...data,
      rating: rate(data.lcp),
    };
  } catch (err) {
    return { url, error: err.message };
  } finally {
    await context.close();
  }
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.urls.length === 0) {
    console.error('Usage: node lcp-diagnostic.js <url> [--form-factor mobile]');
    process.exit(2);
  }

  // Launch Chromium once and reuse it across URLs; a fresh context per
  // URL keeps timing state isolated without re-paying the launch cost.
  const browser = await chromium.launch();
  const results = [];
  try {
    for (const url of args.urls) {
      const result = await diagnoseOne(url, args.formFactor, browser);
      results.push(result);
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));

  // Exit non-zero if any URL failed or was rated poor, so the script
  // can be used in CI.
  const anyBad = results.some(
    (r) => r.error || (r.rating && r.rating !== 'good')
  );
  process.exit(anyBad ? 1 : 0);
}

main();