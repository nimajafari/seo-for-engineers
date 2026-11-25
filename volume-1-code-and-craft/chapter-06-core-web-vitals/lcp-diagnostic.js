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
// LCP entries are not in the performance timeline buffer, so
// performance.getEntriesByType('largest-contentful-paint') is always
// empty. The script installs a PerformanceObserver before any page
// script runs and keeps the latest candidate.
//
// The four sub-parts use the same arithmetic as web-vitals/attribution
// (v6): the resource's requestStart when Timing-Allow-Origin exposes it,
// startTime otherwise, and every boundary capped so the four parts add
// up to the LCP time. For text LCP elements (no resource fetch) the
// resource sub-parts are zero and the rest flows into elementRenderDelay.
//
// This is a lab measurement on an unthrottled machine. Use it to see
// which sub-part dominates, not as a substitute for field data.
//
// Exit codes: 0 every URL rated good, 1 at least one URL rated
// needs-improvement or poor, 2 usage error or a URL that could not be
// measured (and none rated worse than good).
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import { readFileSync, realpathSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

// Playwright device descriptors. Their user agents track the bundled
// Chromium version and do not contain "HeadlessChrome".
export const FORM_FACTORS = {
  desktop: 'Desktop Chrome',
  mobile: 'Pixel 7',
};

const SETTLE_MS = 2_000;

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
  const args = { urls: [], formFactor: 'desktop', urlsFile: null };
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--form-factor' || t === '--urls-file') {
      const value = tokens[++i];
      if (value === undefined || value.startsWith('--')) {
        throw new UsageError(`${t} needs a value`);
      }
      if (t === '--form-factor') args.formFactor = value;
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
  if (!Object.hasOwn(FORM_FACTORS, args.formFactor)) {
    throw new UsageError(
      `--form-factor must be one of ${Object.keys(FORM_FACTORS).join(', ')}`
    );
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

export function rate(lcpMs) {
  if (lcpMs <= 2500) return 'good';
  if (lcpMs <= 4000) return 'needs-improvement';
  return 'poor';
}

// Pick the resource entry that painted the LCP element: the latest
// fetch of that URL that started before the LCP render. Requests made
// after the render cannot be what painted it.
export function pickLcpResource(resources, lcpStartTime) {
  const candidates = resources.filter(
    (r) => (r.requestStart || r.startTime) <= lcpStartTime
  );
  return candidates.length ? candidates[candidates.length - 1] : null;
}

// Four-part LCP decomposition, matching web-vitals/attribution v6.
// All inputs are DOMHighResTimeStamps from the page; the result is in
// milliseconds relative to activation (0 unless prerendered).
export function lcpBreakdown({
  lcpStartTime,
  activationStart = 0,
  responseStart = 0,
  resource = null,
}) {
  const lcp = Math.max(0, lcpStartTime - activationStart);
  const ttfb = Math.max(0, responseStart - activationStart);
  const requestStart = Math.max(
    ttfb,
    resource ? (resource.requestStart || resource.startTime) - activationStart : 0
  );
  const responseEnd = Math.min(
    lcp,
    Math.max(requestStart, resource ? resource.responseEnd - activationStart : 0)
  );
  return {
    lcp,
    subParts: {
      ttfb,
      resourceLoadDelay: requestStart - ttfb,
      resourceLoadDuration: responseEnd - requestStart,
      elementRenderDelay: lcp - responseEnd,
    },
  };
}

// Turns the raw timings read from the page into the report entry.
export function buildReport(url, formFactor, raw) {
  if (!raw.lcp) return { url, formFactor, error: 'no_lcp_entry' };
  const resource = raw.lcp.url
    ? pickLcpResource(raw.resources, raw.lcp.startTime)
    : null;
  const { lcp, subParts } = lcpBreakdown({
    lcpStartTime: raw.lcp.startTime,
    activationStart: raw.activationStart,
    responseStart: raw.responseStart,
    resource,
  });
  const rounded = Object.fromEntries(
    Object.entries(subParts).map(([k, v]) => [k, Math.round(v)])
  );
  return {
    url,
    finalUrl: raw.finalUrl,
    formFactor,
    status: raw.status,
    lcp: Math.round(lcp),
    rating: rate(lcp),
    lcpUrl: raw.lcp.url || null,
    lcpResourceFound: Boolean(resource),
    element: raw.lcp.element,
    subParts: rounded,
    wasPrerenderActivation: raw.activationStart > 0,
  };
}

export function exitCode(results) {
  if (results.some((r) => r.rating && r.rating !== 'good')) return 1;
  if (results.some((r) => r.error)) return 2;
  return 0;
}

// Runs in the page before any page script. Keeps the latest LCP
// candidate, including element details captured while the element is
// still in the DOM.
function observeLcp() {
  window.__lcpDiagnostic = null;
  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const entry = entries[entries.length - 1];
      const el = entry.element;
      window.__lcpDiagnostic = {
        startTime: entry.startTime,
        url: entry.url || '',
        size: entry.size,
        element: el
          ? {
              tag: el.tagName ? el.tagName.toLowerCase() : null,
              id: el.id || null,
              className: typeof el.className === 'string' ? el.className : null,
            }
          : entry.id
            ? { tag: null, id: entry.id, className: null }
            : null,
      };
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch {
    // Browser without LCP support. Reported as no_lcp_entry.
  }
}

function readTimings() {
  const lcp = window.__lcpDiagnostic;
  const nav = performance.getEntriesByType('navigation')[0];
  const resources = lcp && lcp.url
    ? performance
        .getEntriesByType('resource')
        .filter((r) => r.name === lcp.url)
        .map((r) => ({
          startTime: r.startTime,
          requestStart: r.requestStart,
          responseEnd: r.responseEnd,
        }))
    : [];
  return {
    lcp,
    resources,
    activationStart: nav ? nav.activationStart || 0 : 0,
    responseStart: nav ? nav.responseStart : 0,
    finalUrl: location.href,
  };
}

async function diagnoseOne(url, formFactor, browser, devices) {
  const context = await browser.newContext({ ...devices[FORM_FACTORS[formFactor]] });
  await context.addInitScript(observeLcp);
  const page = await context.newPage();
  try {
    const response = await page.goto(url, { waitUntil: 'load', timeout: 30_000 });
    // Wait briefly so late-loading LCP candidates settle.
    await page.waitForTimeout(SETTLE_MS);
    const raw = await page.evaluate(readTimings);
    return buildReport(url, formFactor, { ...raw, status: response?.status() ?? null });
  } catch (err) {
    return { url, formFactor, error: err.message.split('\n')[0] };
  } finally {
    await context.close();
  }
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    if (!(err instanceof UsageError)) throw err;
    console.error(`lcp-diagnostic: ${err.message}`);
    console.error(
      'Usage: node lcp-diagnostic.js [--form-factor desktop|mobile] ' +
        '<url> [...] | --urls <url> [...] | --urls-file <file>'
    );
    return 2;
  }

  const { chromium, devices } = await import('playwright');
  // Launch Chromium once and reuse it across URLs; a fresh context per
  // URL keeps timing state isolated without re-paying the launch cost.
  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    console.error(`lcp-diagnostic: cannot launch Chromium: ${err.message.split('\n')[0]}`);
    console.error('Run `npx playwright install chromium` first.');
    return 2;
  }
  const results = [];
  try {
    for (const url of args.urls) {
      results.push(await diagnoseOne(url, args.formFactor, browser, devices));
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
