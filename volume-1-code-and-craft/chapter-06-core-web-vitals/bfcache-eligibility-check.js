// bfcache-eligibility-check.js
//
// Playwright-based bfcache eligibility checker. Runs two checks for
// each URL:
//
//   1. Passive header check for Cache-Control: no-store. Chrome
//      restores a no-store page only if no cookie changed while the
//      user was away (reason CacheControlNoStoreCookieModified
//      otherwise), so for most logged-in pages it is still a blocker,
//      and other browsers may refuse no-store pages outright. A
//      no-store page is never reported as eligible.
//   2. Active behavioral test that loads the page, navigates away,
//      goes back, and checks whether Chrome restored the page from
//      bfcache. If it did not, Chrome's own reasons are reported.
//
// The behavioral test is the authoritative one for Chrome. Details
// that matter for getting a real answer:
//
//   - Playwright launches Chromium with --disable-back-forward-cache,
//     so the script removes that flag. The default headless shell
//     cannot use bfcache at all (BackForwardCacheDisabledForDelegate),
//     so the script launches the full Chromium build in headless mode
//     (channel: 'chromium').
//   - A restored page keeps its original navigation entry, whose type
//     stays 'navigate'. Restoration is detected from the pageshow
//     event's `persisted` flag instead. A page that was not restored
//     loads again with a 'back_forward' navigation entry.
//   - Reasons come from the DevTools protocol event
//     Page.backForwardCacheNotUsed, the same source as the DevTools
//     bfcache tester, with performance navigation notRestoredReasons
//     as a fallback. The latter often reports only "masked".
//
// Usage:
//   node bfcache-eligibility-check.js https://example.com/
//   node bfcache-eligibility-check.js --urls https://example.com/ https://example.com/products
//   node bfcache-eligibility-check.js --urls-file urls.txt
//   node bfcache-eligibility-check.js --away https://example.com/about https://example.com/
//
// --away sets the page visited between load and back (default
// about:blank). Use a page on your own site to test reasons such as a
// cookie changed by the next page.
//
// Exit codes: 0 every URL eligible, 1 at least one URL not eligible,
// 2 usage error or a URL that could not be tested (and none blocked).
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import { readFileSync, realpathSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const TIMEOUT_MS = 30_000;

export class UsageError extends Error {}

export function readUrlsFile(path) {
  let text;
  try {
    text = readFileSync(path, 'utf-8');
  } catch (err) {
    throw new UsageError(`cannot read --urls-file ${path}: ${err.message}`);
  }
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'));
}

export function parseArgs(tokens) {
  const args = { urls: [], urlsFile: null, away: 'about:blank' };
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--urls-file' || t === '--away') {
      const value = tokens[++i];
      if (value === undefined || value.startsWith('--')) {
        throw new UsageError(`${t} needs a value`);
      }
      if (t === '--away') args.away = value;
      else args.urlsFile = value;
    } else if (t === '--urls') {
      while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
        args.urls.push(tokens[++i]);
      }
    } else if (t.startsWith('--')) {
      throw new UsageError(`unknown option ${t}`);
    } else {
      args.urls.push(t);
    }
  }
  if (args.urlsFile) args.urls.push(...readUrlsFile(args.urlsFile));
  for (const url of args.urls) {
    if (!/^https?:\/\//i.test(url)) {
      throw new UsageError(`not an absolute http(s) URL: ${url}`);
    }
  }
  if (args.urls.length === 0) throw new UsageError('no URLs given');
  return args;
}

// True when the Cache-Control header carries the no-store directive.
// Matches the directive token, not a substring of another directive.
export function hasNoStore(cacheControl) {
  if (!cacheControl) return false;
  return cacheControl
    .split(',')
    .some((d) => d.trim().split('=')[0].trim().toLowerCase() === 'no-store');
}

// Flattens a NotRestoredReasons tree (main frame plus children) into a
// list of reason strings.
export function flattenNotRestoredReasons(node) {
  if (!node) return [];
  const own = (node.reasons || []).map((r) => r.reason).filter(Boolean);
  return own.concat(...(node.children || []).map(flattenNotRestoredReasons));
}

// DevTools explanation types, from "the page can fix this" to "the
// browser or the test environment caused this".
const EXPLANATION_SEVERITY = {
  PageSupportNeeded: 'high',
  SupportPending: 'medium',
  Circumstantial: 'low',
};

// Builds the per-URL result from what the browser observed.
export function classify(observed) {
  const result = {
    url: observed.url,
    status: observed.status ?? null,
    cacheControl: observed.cacheControl ?? null,
    headerCheck: 'unknown',
    behavioralCheck: 'unknown',
    restored: null,
    notRestoredReasons: [],
    issues: [],
    eligible: false,
  };

  if (observed.error) {
    result.behavioralCheck = 'error';
    result.issues.push({ severity: 'high', type: 'check_failed', message: observed.error });
    return result;
  }

  if (hasNoStore(result.cacheControl)) {
    result.headerCheck = 'no_store';
    result.issues.push({
      severity: 'medium',
      type: 'cache_control_no_store',
      message:
        'Cache-Control: no-store. Chrome refuses to restore this page from ' +
        'bfcache whenever a cookie changed while the user was away, and other ' +
        'browsers may refuse it outright. Remove no-store if the page is safe ' +
        'to cache.',
      detail: result.cacheControl,
    });
  } else {
    result.headerCheck = 'ok';
  }

  result.restored = observed.persisted === true;
  result.behavioralCheck = result.restored ? 'restored' : 'not_restored';

  if (!result.restored) {
    const explanations = observed.explanations || [];
    result.notRestoredReasons = flattenNotRestoredReasons(observed.notRestoredReasons);
    for (const e of explanations) {
      result.issues.push({
        severity: EXPLANATION_SEVERITY[e.type] || 'medium',
        type: e.reason,
        message: `Chrome did not restore the page (${e.type}).`,
        detail: e.context ?? null,
      });
    }
    if (explanations.length === 0) {
      for (const reason of result.notRestoredReasons) {
        result.issues.push({
          severity: 'high',
          type: reason,
          message: 'Chrome did not restore the page (notRestoredReasons).',
        });
      }
    }
    if (explanations.length === 0 && result.notRestoredReasons.length === 0) {
      result.issues.push({
        severity: 'high',
        type: 'not_restored_unknown',
        message: 'Chrome did not restore the page and reported no reason.',
      });
    }
  }

  result.eligible = result.restored && result.headerCheck === 'ok';
  return result;
}

export function statusLabel(result) {
  if (result.behavioralCheck === 'error') return 'ERROR';
  return result.eligible ? 'OK' : 'BLOCKED';
}

export function exitCode(results) {
  const labels = results.map(statusLabel);
  if (labels.includes('BLOCKED')) return 1;
  if (labels.includes('ERROR')) return 2;
  return 0;
}

// Runs in every document before page scripts: records each pageshow,
// whose `persisted` flag is true only for a bfcache restore.
function recordPageshow() {
  window.__bfcachePageshows = [];
  addEventListener('pageshow', (event) => {
    window.__bfcachePageshows.push(event.persisted);
  });
}

async function checkOne(url, away, browser) {
  const observed = { url };
  const context = await browser.newContext();
  await context.addInitScript(recordPageshow);
  const page = await context.newPage();
  const explanations = [];
  try {
    const cdp = await context.newCDPSession(page);
    await cdp.send('Page.enable');
    cdp.on('Page.backForwardCacheNotUsed', (event) => {
      explanations.push(...(event.notRestoredExplanations || []));
    });

    // Step 1: load the target and capture the response headers.
    const response = await page.goto(url, { waitUntil: 'load', timeout: TIMEOUT_MS });
    observed.status = response?.status() ?? null;
    observed.cacheControl = response?.headers()['cache-control'] ?? null;

    // Step 2: navigate away and back. A restore fires pageshow but no
    // load event, so wait for the commit and then for pageshow.
    await page.goto(away, { waitUntil: 'load', timeout: TIMEOUT_MS });
    await page.goBack({ waitUntil: 'commit', timeout: TIMEOUT_MS });
    await page.waitForFunction(
      () =>
        document.readyState === 'complete' &&
        Array.isArray(window.__bfcachePageshows) &&
        window.__bfcachePageshows.length > 0,
      null,
      { timeout: TIMEOUT_MS }
    );
    const state = await page.evaluate(() => {
      const nav = performance.getEntriesByType('navigation')[0];
      const nrr = nav && nav.notRestoredReasons;
      return {
        persisted: window.__bfcachePageshows.at(-1) === true,
        notRestoredReasons: nrr ? nrr.toJSON() : null,
      };
    });
    Object.assign(observed, state, { explanations });
  } catch (err) {
    observed.error = err.message.split('\n')[0];
  } finally {
    await context.close();
  }
  return classify(observed);
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    if (!(err instanceof UsageError)) throw err;
    console.error(`bfcache-eligibility-check: ${err.message}`);
    console.error(
      'Usage: node bfcache-eligibility-check.js [--away <url>] ' +
        '<url> [...] | --urls <url> [...] | --urls-file <file>'
    );
    return 2;
  }

  const { chromium } = await import('playwright');
  // Launch Chromium once and reuse it across URLs; each check runs in a
  // fresh context so navigation history and bfcache state stay isolated.
  let browser;
  try {
    browser = await chromium.launch({
      channel: 'chromium',
      ignoreDefaultArgs: ['--disable-back-forward-cache'],
    });
  } catch (err) {
    console.error(
      `bfcache-eligibility-check: cannot launch Chromium: ${err.message.split('\n')[0]}`
    );
    console.error('Run `npx playwright install chromium` first.');
    return 2;
  }
  const results = [];
  try {
    for (const url of args.urls) {
      const result = await checkOne(url, args.away, browser);
      results.push(result);
      console.error(
        `${statusLabel(result)}\t${result.url}\t` +
          result.issues.map((i) => i.type).join(',')
      );
    }
  } finally {
    await browser.close();
  }

  console.log(JSON.stringify(results.length === 1 ? results[0] : results, null, 2));
  return exitCode(results);
}

const invokedDirectly =
  process.argv[1] &&
  import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href;
if (invokedDirectly) {
  process.exitCode = await main();
}
