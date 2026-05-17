// bfcache-eligibility-check.js
//
// Playwright-based bfcache eligibility checker. Runs two checks for
// each URL:
//
//   1. Passive header check for Cache-Control: no-store, the most
//      common bfcache blocker that ships in a configuration mistake.
//   2. Active behavioral test that navigates to the page, navigates
//      away, navigates back, and reads
//      performance.getEntriesByType('navigation')[0].notRestoredReasons
//      to see what Chrome itself reported.
//
// The behavioral test is the authoritative one. Chrome's reasons list
// is what bfcache actually evaluated, not a heuristic.
//
// Usage:
//   node bfcache-eligibility-check.js https://example.com/
//   node bfcache-eligibility-check.js --urls https://example.com/ https://example.com/products
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import { chromium } from 'playwright';
import process from 'node:process';

function parseArgs(argv) {
  const args = { urls: [] };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--urls') {
      while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
        args.urls.push(tokens[++i]);
      }
    } else if (t.startsWith('http')) {
      args.urls.push(t);
    }
  }
  return args;
}

async function checkOne(url) {
  const result = {
    url,
    cacheControl: null,
    headerCheck: 'unknown',
    behavioralCheck: 'unknown',
    notRestoredReasons: null,
    issues: [],
  };

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // Step 1: navigate to the target and capture response headers.
    const response = await page.goto(url, {
      waitUntil: 'load',
      timeout: 30_000,
    });
    const headers = response?.headers() || {};
    result.cacheControl = headers['cache-control'] || null;

    if (
      result.cacheControl &&
      result.cacheControl.toLowerCase().includes('no-store')
    ) {
      result.headerCheck = 'blocked';
      result.issues.push({
        severity: 'high',
        type: 'cache_control_no_store',
        message:
          'Cache-Control: no-store on the response makes this page ' +
          'bfcache-ineligible. Remove no-store if the page is safe to cache.',
        detail: result.cacheControl,
      });
    } else {
      result.headerCheck = 'ok';
    }

    // Step 2: behavioral test. Navigate away, then back, then read
    // notRestoredReasons from the restored page's navigation entry.
    try {
      await page.goto('about:blank', { waitUntil: 'load' });
      await page.goBack({ waitUntil: 'load', timeout: 30_000 });
      // Give the navigation timing API a moment to materialize.
      await page.waitForTimeout(500);

      const behavior = await page.evaluate(() => {
        const navEntry = performance.getEntriesByType('navigation')[0];
        return {
          type: navEntry?.type || null,
          notRestoredReasons: navEntry?.notRestoredReasons || null,
        };
      });

      // back_forward + no notRestoredReasons (or empty) means bfcache
      // restored the page. Otherwise the reasons tell us why not.
      const reasons = behavior.notRestoredReasons;
      const restored =
        behavior.type === 'back_forward' &&
        (!reasons || !reasons.reasons || reasons.reasons.length === 0);

      if (restored) {
        result.behavioralCheck = 'restored';
      } else {
        result.behavioralCheck = 'not_restored';
        result.notRestoredReasons = reasons;
        if (reasons?.reasons?.length) {
          for (const r of reasons.reasons) {
            result.issues.push({
              severity: 'high',
              type: r.reason || 'unknown',
              message: 'Chrome reported this bfcache blocker.',
              detail: r,
            });
          }
        }
      }
    } catch (err) {
      result.behavioralCheck = 'error';
      result.issues.push({
        severity: 'low',
        type: 'behavioral_test_failed',
        message: err.message,
      });
    }
  } catch (err) {
    result.issues.push({
      severity: 'high',
      type: 'navigation_failed',
      message: err.message,
    });
  } finally {
    await browser.close();
  }

  result.eligible =
    result.headerCheck === 'ok' && result.behavioralCheck === 'restored';
  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.urls.length === 0) {
    console.error('Usage: node bfcache-eligibility-check.js <url> [<url> ...]');
    process.exit(2);
  }

  const results = [];
  for (const url of args.urls) {
    const result = await checkOne(url);
    results.push(result);

    const status = result.eligible ? 'OK' : 'BLOCKED';
    console.error(
      `${status}\t${result.url}\t` +
        result.issues.map((i) => i.type).join(',')
    );
  }

  console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));

  const anyBlocked = results.some((r) => !r.eligible);
  process.exit(anyBlocked ? 1 : 0);
}

main();