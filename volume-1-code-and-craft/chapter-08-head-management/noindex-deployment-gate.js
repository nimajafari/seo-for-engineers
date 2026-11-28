// noindex-deployment-gate.js
//
// CI gate for accidental noindex deployments. Designed to run before
// a production deployment against the staging build of a release
// candidate. Failure Mode 4 in Chapter 8 of SEO for Engineers,
// Volume 1, is the most expensive head-management failure. This
// script is intended to be the blocking gate that prevents it.
//
// For each URL the script runs two checks.
//
//   1. HTTP-level: the URL is fetched (following redirects). An HTTP
//      error status blocks the URL, since a page that answers 404 or
//      500 is not indexable either. Every X-Robots-Tag response header
//      is inspected for a noindex or none directive.
//   2. Rendered DOM: the page is loaded in headless Chromium. After
//      the load event the gate waits for the network to go quiet
//      (capped at 5 seconds, since analytics beacons can keep it busy
//      forever) plus --settle-ms, then reads every
//      <meta name="robots"> and <meta name="googlebot"> tag, with the
//      name matched case-insensitively as Google does. This catches
//      noindex injected by client-side JavaScript after initial render.
//
// Directives are parsed, not substring-matched: "noindex" and "none"
// block, "max-image-preview:none" does not, and a "googlebot: noindex"
// user-agent prefix in X-Robots-Tag still counts.
//
// Usage:
//   node noindex-deployment-gate.js \
//     --urls https://staging.example.com/ https://staging.example.com/products/sample
//   node noindex-deployment-gate.js --urls-file staging-urls.txt
//   node noindex-deployment-gate.js --settle-ms 2000 https://staging.example.com/
//
// Exit codes: 0 every URL passed, 1 at least one URL carries noindex,
// 2 usage error or a URL that could not be checked (fetch or page load
// failed, or HTTP status >= 400) and no noindex elsewhere. Any non-zero
// exit should block the deployment.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { readFileSync, realpathSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

const NAVIGATION_TIMEOUT_MS = 30_000;
const NETWORK_IDLE_CAP_MS = 5_000;
const DEFAULT_SETTLE_MS = 500;

// Robots directives that carry a value after a colon. Any other
// "word:" prefix names a user agent, as in "googlebot: noindex".
const VALUE_DIRECTIVES = new Set([
  'max-snippet',
  'max-image-preview',
  'max-video-preview',
  'unavailable_after',
]);
// Google documents "none" as equivalent to "noindex, nofollow".
const NOINDEX_DIRECTIVES = new Set(['noindex', 'none']);

// The rendered-DOM meta names the gate reads, lowercased.
export const ROBOTS_META_NAMES = ['robots', 'googlebot'];

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
  const args = { urls: [], urlsFile: null, settleMs: DEFAULT_SETTLE_MS };
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--urls-file' || t === '--settle-ms') {
      const value = tokens[++i];
      if (value === undefined || value.startsWith('--')) {
        throw new UsageError(`${t} needs a value`);
      }
      if (t === '--urls-file') {
        args.urlsFile = value;
      } else {
        if (!/^\d+$/.test(value)) {
          throw new UsageError('--settle-ms must be a whole number of milliseconds');
        }
        args.settleMs = Number(value);
      }
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

// Splits a robots meta content or X-Robots-Tag value into
// { agent, directive } pairs, directive names lowercased.
export function robotsDirectives(value) {
  const pairs = [];
  let agent = null;
  for (let token of String(value ?? '').split(/[,;]/)) {
    token = token.trim();
    let colon = token.indexOf(':');
    if (colon !== -1) {
      const name = token.slice(0, colon).trim().toLowerCase();
      if (!VALUE_DIRECTIVES.has(name)) {
        agent = name;
        token = token.slice(colon + 1).trim();
        colon = token.indexOf(':');
      }
    }
    if (colon !== -1) {
      pairs.push({ agent, directive: token.slice(0, colon).trim().toLowerCase() });
    } else {
      for (const word of token.toLowerCase().split(/\s+/).filter(Boolean)) {
        pairs.push({ agent, directive: word });
      }
    }
  }
  return pairs;
}

// True when the value carries noindex or none, for any user agent.
export function hasNoindex(value) {
  return robotsDirectives(value).some((p) => NOINDEX_DIRECTIVES.has(p.directive));
}

// Turns what was observed for one URL into the list of blockers. Pure,
// so the rules are testable without a browser.
//   observed.http: { status, xRobotsTag: string[] } or { error }
//   observed.dom:  { status, meta: [{ name, content }] } or { error }
export function evaluate(observed) {
  const blockers = [];
  const { http, dom } = observed;

  if (http?.error) {
    blockers.push({ type: 'http_fetch_failed', message: `HTTP fetch failed: ${http.error}` });
  } else if (http) {
    if (http.status >= 400) {
      blockers.push({
        type: 'http_error_status',
        message: `URL returned HTTP ${http.status}; an error page is not indexable.`,
      });
    }
    const noindexHeaders = (http.xRobotsTag ?? []).filter(hasNoindex);
    if (noindexHeaders.length > 0) {
      blockers.push({
        type: 'x_robots_tag_noindex',
        message: 'X-Robots-Tag response header contains noindex.',
        detail: noindexHeaders.join(' | '),
      });
    }
  }

  if (dom?.error) {
    blockers.push({ type: 'page_load_failed', message: `Page load failed: ${dom.error}` });
  } else if (dom) {
    for (const name of ROBOTS_META_NAMES) {
      const noindexTags = dom.meta
        .filter((m) => m.name === name && hasNoindex(m.content))
        .map((m) => m.content);
      if (noindexTags.length > 0) {
        blockers.push({
          type: `meta_${name === 'googlebot' ? 'googlebot' : 'robots'}_noindex`,
          message: `<meta name="${name}"> contains noindex.`,
          detail: noindexTags.join(' | '),
        });
      }
    }
  }
  return blockers;
}

const NOINDEX_TYPES = new Set([
  'x_robots_tag_noindex',
  'meta_robots_noindex',
  'meta_googlebot_noindex',
]);

export function statusLabel(result) {
  if (result.blockers.length === 0) return 'PASS';
  return result.blockers.some((b) => NOINDEX_TYPES.has(b.type)) ? 'BLOCKED' : 'ERROR';
}

export function exitCode(results) {
  const labels = results.map(statusLabel);
  if (labels.includes('BLOCKED')) return 1;
  if (labels.includes('ERROR')) return 2;
  return 0;
}

// Runs in the page: every robots-family meta tag, name lowercased.
function collectRobotsMeta(names) {
  return Array.from(document.querySelectorAll('meta[name]'))
    .map((m) => ({
      name: m.getAttribute('name').trim().toLowerCase(),
      content: m.getAttribute('content') ?? '',
    }))
    .filter((m) => names.includes(m.name));
}

async function observeHttp(url, requestContext) {
  try {
    const response = await requestContext.get(url, { timeout: NAVIGATION_TIMEOUT_MS });
    const xRobotsTag = response
      .headersArray()
      .filter((h) => h.name.toLowerCase() === 'x-robots-tag')
      .map((h) => h.value);
    return { status: response.status(), xRobotsTag };
  } catch (err) {
    return { error: err.message.split('\n')[0] };
  }
}

async function observeDom(url, browser, settleMs) {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    const response = await page.goto(url, {
      waitUntil: 'load',
      timeout: NAVIGATION_TIMEOUT_MS,
    });
    // networkidle alone never settles on pages with beacons or
    // long-polling, so it is capped; the settle delay then covers
    // scripts that add tags after the last response.
    await page
      .waitForLoadState('networkidle', { timeout: NETWORK_IDLE_CAP_MS })
      .catch(() => {});
    if (settleMs > 0) await page.waitForTimeout(settleMs);
    return {
      status: response?.status() ?? null,
      meta: await page.evaluate(collectRobotsMeta, ROBOTS_META_NAMES),
    };
  } catch (err) {
    return { error: err.message.split('\n')[0] };
  } finally {
    await context.close();
  }
}

async function checkOne(url, requestContext, browser, settleMs) {
  const http = await observeHttp(url, requestContext);
  const dom = await observeDom(url, browser, settleMs);
  const blockers = evaluate({ http, dom });
  return {
    url,
    status: http.status ?? null,
    xRobotsTag: http.xRobotsTag ?? [],
    robotsMeta: dom.meta ?? [],
    blockers,
    passed: blockers.length === 0,
  };
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    if (!(err instanceof UsageError)) throw err;
    console.error(`noindex-deployment-gate: ${err.message}`);
    console.error(
      'Usage: node noindex-deployment-gate.js [--settle-ms N] ' +
        '<url> [...] | --urls <url> [...] | --urls-file <file>'
    );
    return 2;
  }

  const { chromium, request: playwrightRequest } = await import('playwright');
  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    console.error(
      `noindex-deployment-gate: cannot launch Chromium: ${err.message.split('\n')[0]}`
    );
    console.error('Run `npx playwright install chromium` first.');
    return 2;
  }
  const requestContext = await playwrightRequest.newContext();

  const results = [];
  try {
    for (const url of args.urls) {
      const result = await checkOne(url, requestContext, browser, args.settleMs);
      results.push(result);
      const summary = result.blockers.map((b) => b.type).join(',') || 'none';
      console.error(`${statusLabel(result)}\t${url}\t${summary}`);
    }
  } finally {
    await requestContext.dispose();
    await browser.close();
  }

  const out = {
    results,
    summary: {
      urls_checked: results.length,
      urls_blocked: results.filter((r) => !r.passed).length,
    },
  };
  console.log(JSON.stringify(out, null, 2));
  return exitCode(results);
}

const invokedDirectly =
  process.argv[1] &&
  import.meta.url === pathToFileURL(realpathSync(process.argv[1])).href;
if (invokedDirectly) {
  // exitCode, not process.exit(), so piped stdout is flushed first.
  process.exitCode = await main();
}
