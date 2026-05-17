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
//   1. HTTP-level: the response's X-Robots-Tag header is inspected.
//      If it contains "noindex" (case-insensitive), the URL fails.
//   2. Rendered DOM: the page is loaded in headless Chromium and the
//      rendered DOM is inspected for <meta name="robots"> and
//      <meta name="googlebot"> tags containing "noindex". This catches
//      the case where noindex is injected by client-side JavaScript
//      after initial render.
//
// Exits non-zero if any URL has noindex set. Designed to be wired
// directly into a deployment pipeline as a required check.
//
// Usage:
//   node noindex-deployment-gate.js \
//     --urls https://staging.example.com/ https://staging.example.com/products/sample
//   node noindex-deployment-gate.js --urls-file staging-urls.txt
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { chromium, request as playwrightRequest } from 'playwright';
import { readFileSync } from 'node:fs';
import process from 'node:process';

function parseArgs(argv) {
  const args = { urls: [], urlsFile: null };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--urls') {
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

function hasNoindex(value) {
  if (!value) return false;
  return value.toLowerCase().includes('noindex');
}

async function checkOne(url, requestContext, browser) {
  const result = {
    url,
    xRobotsTag: null,
    metaRobots: null,
    metaGoogleBot: null,
    blockers: [],
  };

  // HTTP-level check via a real GET so X-Robots-Tag is captured.
  try {
    const response = await requestContext.get(url, { timeout: 30_000 });
    const headers = response.headers();
    result.xRobotsTag = headers['x-robots-tag'] || null;
    if (hasNoindex(result.xRobotsTag)) {
      result.blockers.push({
        type: 'x_robots_tag_noindex',
        message: `X-Robots-Tag response header contains noindex.`,
        detail: result.xRobotsTag,
      });
    }
  } catch (err) {
    result.blockers.push({
      type: 'http_fetch_failed',
      message: `HTTP fetch failed: ${err.message}`,
    });
  }

  // Rendered-DOM check.
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30_000 });
    const data = await page.evaluate(() => {
      const get = (selector) =>
        document.querySelector(selector)?.getAttribute('content') ?? null;
      return {
        robots: get('meta[name="robots"]'),
        googleBot: get('meta[name="googlebot"]'),
      };
    });
    result.metaRobots = data.robots;
    result.metaGoogleBot = data.googleBot;

    if (hasNoindex(result.metaRobots)) {
      result.blockers.push({
        type: 'meta_robots_noindex',
        message: `<meta name="robots"> contains noindex.`,
        detail: result.metaRobots,
      });
    }
    if (hasNoindex(result.metaGoogleBot)) {
      result.blockers.push({
        type: 'meta_googlebot_noindex',
        message: `<meta name="googlebot"> contains noindex.`,
        detail: result.metaGoogleBot,
      });
    }
  } catch (err) {
    result.blockers.push({
      type: 'page_load_failed',
      message: `Page load failed: ${err.message}`,
    });
  } finally {
    await context.close();
  }

  result.passed = result.blockers.length === 0;
  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.urls.length === 0) {
    console.error(
      'Usage: node noindex-deployment-gate.js --urls <url> [<url> ...]'
    );
    console.error('       node noindex-deployment-gate.js --urls-file urls.txt');
    process.exit(2);
  }

  const browser = await chromium.launch();
  const requestContext = await playwrightRequest.newContext();

  const results = [];
  try {
    for (const url of args.urls) {
      const result = await checkOne(url, requestContext, browser);
      results.push(result);
      const status = result.passed ? 'PASS' : 'BLOCKED';
      const summary = result.blockers
        .map((b) => b.type)
        .join(',') || 'none';
      console.error(`${status}\t${url}\t${summary}`);
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

  process.exit(out.summary.urls_blocked > 0 ? 1 : 0);
}

main();