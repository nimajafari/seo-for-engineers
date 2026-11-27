// heading-hierarchy-validator.js
//
// Playwright-based heading hierarchy validator. Loads a URL in
// headless Chromium and validates the rendered DOM's heading outline
// against the rules from Chapter 7 of SEO for Engineers, Volume 1.
//
// It runs against the rendered DOM, not the raw HTML response, so it
// catches headings injected by JavaScript at hydration time, which the
// Python auditor would miss. After the load event it waits for the
// network to go quiet (capped at 5 seconds, since analytics beacons
// and long-polling can keep it busy forever) plus --settle-ms, so
// headings rendered from a client-side fetch are in the outline.
//
// Headings are read in flat-tree order: the content of open shadow
// roots (web components, declarative shadow DOM) and slotted light-DOM
// content is included where it renders, which is how Google's renderer
// flattens a page. Closed shadow roots cannot be read.
//
// Checks:
//   - Exactly one <h1> per page
//   - No skipped heading levels (h2 followed by h4 without h3)
//   - Headings not inside <aside>, <nav>, or common UI-component
//     ancestors (role=dialog/menu/tooltip, class names matching card,
//     modal, dialog, popover, dropdown, sidebar, widget, tile)
//
// Usage:
//   node heading-hierarchy-validator.js https://example.com/
//   node heading-hierarchy-validator.js --urls https://example.com/ https://example.com/products
//   node heading-hierarchy-validator.js --urls-file urls.txt
//   node heading-hierarchy-validator.js --settle-ms 3000 https://example.com/
//
// Exit codes: 0 no high-severity findings, 1 at least one URL with a
// high-severity finding, 2 usage error or a URL that could not be
// validated (navigation failed or HTTP status >= 400) and no
// high-severity findings elsewhere.
//
// Reference: SEO for Engineers, Volume 1, Chapter 7.

import { readFileSync, realpathSync } from 'node:fs';
import process from 'node:process';
import { pathToFileURL } from 'node:url';

// Keep these in sync with UI_COMPONENT_INDICATORS and UI_ROLES in
// semantic-html-auditor.py so the two tools agree on what a
// UI-component ancestor looks like.
export const UI_COMPONENT_INDICATORS = [
  'card', 'modal', 'dialog', 'popover', 'tooltip', 'dropdown',
  'menu', 'sidebar', 'widget', 'banner', 'tile',
];
export const UI_ROLES = new Set([
  'dialog', 'alertdialog', 'menu', 'menuitem', 'tooltip',
]);

const NAVIGATION_TIMEOUT_MS = 30_000;
const NETWORK_IDLE_CAP_MS = 5_000;
const DEFAULT_SETTLE_MS = 500;

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

// The nearest ancestor that looks like a UI component, or null.
// `ancestors` is ordered nearest first and excludes <body> and <html>.
export function findUiComponent(ancestors) {
  for (const a of ancestors) {
    if (UI_ROLES.has((a.role || '').toLowerCase())) return a;
    const cls = (a.className || '').toLowerCase();
    if (UI_COMPONENT_INDICATORS.some((token) => cls.includes(token))) return a;
  }
  return null;
}

// Turns the collected headings into the report's heading list and
// findings. Pure, so the rules are testable without a browser.
export function evaluateHeadings(collected) {
  const headings = collected.map((h) => {
    const ui = findUiComponent(h.ancestors);
    return {
      tag: `h${h.level}`,
      text: h.text,
      id: h.id,
      className: h.className,
      level: h.level,
      inShadowDom: h.inShadowDom,
      insideAside: h.ancestors.some((a) => a.tag === 'aside'),
      insideNav: h.ancestors.some((a) => a.tag === 'nav'),
      insideUIComponent: ui !== null,
      uiComponentClass: ui ? ui.className || `[role=${ui.role}]` : null,
    };
  });

  const findings = [];
  const h1s = headings.filter((h) => h.level === 1);
  if (h1s.length === 0) {
    findings.push({
      severity: 'high',
      rule: 'missing_h1',
      message: 'Page has no <h1> element in the rendered DOM.',
    });
  } else if (h1s.length > 1) {
    findings.push({
      severity: 'high',
      rule: 'multiple_h1',
      message: `Page has ${h1s.length} <h1> elements. A single <h1> ` +
        `per page is the recommended pattern.`,
      element: h1s[1],
    });
  }

  let lastLevel = null;
  for (const h of headings) {
    if (lastLevel !== null && h.level > lastLevel + 1) {
      findings.push({
        severity: 'medium',
        rule: 'skipped_heading_level',
        message: `Heading level jumped from h${lastLevel} to h${h.level} ` +
          `without an intervening h${lastLevel + 1}.`,
        element: h,
      });
    }
    lastLevel = h.level;
  }

  for (const h of headings) {
    if (h.insideAside) {
      findings.push({
        severity: 'low',
        rule: 'heading_inside_aside',
        message: `<h${h.level}> inside <aside>. Aside headings appear in ` +
          `the document outline as sub-topics of the nearest preceding ` +
          `heading, which may not be the intent.`,
        element: h,
      });
    }
    if (h.insideNav) {
      findings.push({
        severity: 'medium',
        rule: 'heading_inside_nav',
        message: `<h${h.level}> inside <nav>. Navigation regions should ` +
          `use aria-label or aria-labelledby on the <nav> element, not ` +
          `internal heading elements.`,
        element: h,
      });
    }
    if (h.insideUIComponent) {
      findings.push({
        severity: 'low',
        rule: 'heading_inside_ui_component',
        message: `<h${h.level}> inside a UI-component ancestor ` +
          `("${h.uiComponentClass}"). UI component titles usually should ` +
          `not be heading elements.`,
        element: h,
      });
    }
  }
  return { headings, findings };
}

export function countFindings(findings) {
  const count = (s) => findings.filter((f) => f.severity === s).length;
  return { high: count('high'), medium: count('medium'), low: count('low') };
}

export function statusLabel(result) {
  if (result.error) return 'ERROR';
  return result.counts.high === 0 ? 'OK' : 'BLOCKED';
}

export function exitCode(results) {
  const labels = results.map(statusLabel);
  if (labels.includes('BLOCKED')) return 1;
  if (labels.includes('ERROR')) return 2;
  return 0;
}

// Runs in the page. Walks the flat tree (open shadow roots replace a
// host's light children; slots render their assigned elements, or
// their fallback children) and records each heading with its
// ancestors below <body>, nearest first.
function collectHeadings() {
  const out = [];
  const summary = (el) => ({
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute('role'),
    className:
      typeof el.className === 'string' && el.className
        ? el.className.slice(0, 80)
        : null,
  });
  function children(el) {
    if (el.shadowRoot) return Array.from(el.shadowRoot.children);
    if (el.tagName === 'SLOT') {
      const assigned = el.assignedElements({ flatten: true });
      return assigned.length ? assigned : Array.from(el.children);
    }
    return Array.from(el.children);
  }
  function walk(el, ancestors) {
    const match = /^H([1-6])$/.exec(el.tagName);
    if (match) {
      out.push({
        level: Number(match[1]),
        text: (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
        id: el.id || null,
        className: summary(el).className,
        inShadowDom: el.getRootNode() instanceof ShadowRoot,
        ancestors: [...ancestors].reverse(),
      });
    }
    const childAncestors = [...ancestors, summary(el)];
    for (const child of children(el)) walk(child, childAncestors);
  }
  if (document.body) {
    for (const child of children(document.body)) walk(child, []);
  }
  return out;
}

async function validateOne(url, browser, settleMs) {
  const result = { url, status: null, finalUrl: null, headings: [], findings: [] };
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    const response = await page.goto(url, {
      waitUntil: 'load',
      timeout: NAVIGATION_TIMEOUT_MS,
    });
    result.status = response?.status() ?? null;
    result.finalUrl = page.url();
    if (result.status !== null && result.status >= 400) {
      result.error = `HTTP ${result.status}`;
    } else {
      // networkidle alone never settles on pages with beacons or
      // long-polling, so it is capped; the settle delay then covers
      // rendering that follows the last response.
      await page
        .waitForLoadState('networkidle', { timeout: NETWORK_IDLE_CAP_MS })
        .catch(() => {});
      if (settleMs > 0) await page.waitForTimeout(settleMs);
      const { headings, findings } = evaluateHeadings(await page.evaluate(collectHeadings));
      result.headings = headings;
      result.findings = findings;
    }
  } catch (err) {
    result.error = err.message.split('\n')[0];
  } finally {
    await context.close();
  }
  result.counts = countFindings(result.findings);
  return result;
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (err) {
    if (!(err instanceof UsageError)) throw err;
    console.error(`heading-hierarchy-validator: ${err.message}`);
    console.error(
      'Usage: node heading-hierarchy-validator.js [--settle-ms N] ' +
        '<url> [...] | --urls <url> [...] | --urls-file <file>'
    );
    return 2;
  }

  const { chromium } = await import('playwright');
  // Launch the browser once and reuse it across URLs. A fresh context
  // per URL keeps state isolated without paying the browser launch cost
  // on every page.
  let browser;
  try {
    browser = await chromium.launch();
  } catch (err) {
    console.error(
      `heading-hierarchy-validator: cannot launch Chromium: ${err.message.split('\n')[0]}`
    );
    console.error('Run `npx playwright install chromium` first.');
    return 2;
  }
  const results = [];
  try {
    for (const url of args.urls) {
      const result = await validateOne(url, browser, args.settleMs);
      results.push(result);
      const { high, medium, low } = result.counts;
      console.error(
        `${statusLabel(result)}\t${result.url}\t` +
          (result.error ? result.error : `h=${high} m=${medium} l=${low}`)
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
