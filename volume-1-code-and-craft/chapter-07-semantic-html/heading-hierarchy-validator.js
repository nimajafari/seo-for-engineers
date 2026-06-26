// heading-hierarchy-validator.js
//
// Playwright-based heading hierarchy validator. Loads a URL in
// headless Chromium and validates the rendered DOM's heading outline
// against the rules from Chapter 7 of SEO for Engineers, Volume 1.
//
// It runs against the rendered DOM, not the raw HTML response, so it
// catches headings injected by JavaScript at hydration time, which the
// Python auditor would miss.
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
//
// Reference: SEO for Engineers, Volume 1, Chapter 7.

import { chromium } from 'playwright';
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

async function validateOne(url, browser) {
  const result = {
    url,
    headings: [],
    findings: [],
  };

  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // 'load' rather than 'networkidle': the heading outline is present
    // at load, and networkidle never settles on pages with analytics
    // beacons or long-polling, burning the timeout for no added signal.
    await page.goto(url, { waitUntil: 'load', timeout: 30_000 });

    const data = await page.evaluate(() => {
      // Keep this list in sync with UI_COMPONENT_INDICATORS in
      // semantic-html-auditor.py so the two tools agree on what a
      // UI-component ancestor looks like.
      const UI_COMPONENT_INDICATORS = [
        'card', 'modal', 'dialog', 'popover', 'tooltip', 'dropdown',
        'menu', 'sidebar', 'widget', 'banner', 'tile',
      ];
      const UI_ROLES = new Set([
        'dialog', 'alertdialog', 'menu', 'menuitem', 'tooltip',
      ]);

      function elementSummary(el) {
        return {
          tag: el.tagName.toLowerCase(),
          text: (el.textContent || '').trim().slice(0, 80),
          id: el.id || null,
          className:
            typeof el.className === 'string' && el.className
              ? el.className.slice(0, 80)
              : null,
        };
      }

      function isInsideUIComponent(el) {
        let parent = el.parentElement;
        while (parent && parent !== document.body) {
          const role = (parent.getAttribute('role') || '').toLowerCase();
          if (UI_ROLES.has(role)) return parent;
          const cls =
            (typeof parent.className === 'string'
              ? parent.className
              : '') || '';
          const lower = cls.toLowerCase();
          for (const token of UI_COMPONENT_INDICATORS) {
            if (lower.includes(token)) return parent;
          }
          parent = parent.parentElement;
        }
        return null;
      }

      function isInsideTag(el, tagName) {
        let parent = el.parentElement;
        while (parent && parent !== document.body) {
          if (parent.tagName.toLowerCase() === tagName) return parent;
          parent = parent.parentElement;
        }
        return null;
      }

      const headings = Array.from(
        document.querySelectorAll('h1, h2, h3, h4, h5, h6')
      );

      const headingInfo = headings.map((h) => {
        const aside = isInsideTag(h, 'aside');
        const nav = isInsideTag(h, 'nav');
        const ui = isInsideUIComponent(h);
        return {
          ...elementSummary(h),
          level: parseInt(h.tagName[1], 10),
          insideAside: aside !== null,
          insideNav: nav !== null,
          insideUIComponent: ui !== null,
          uiComponentClass: ui ? elementSummary(ui).className : null,
        };
      });

      return { headings: headingInfo };
    });

    result.headings = data.headings;

    // h1 checks
    const h1s = data.headings.filter((h) => h.level === 1);
    if (h1s.length === 0) {
      result.findings.push({
        severity: 'high',
        rule: 'missing_h1',
        message: 'Page has no <h1> element in the rendered DOM.',
      });
    } else if (h1s.length > 1) {
      result.findings.push({
        severity: 'high',
        rule: 'multiple_h1',
        message: `Page has ${h1s.length} <h1> elements. A single <h1> ` +
          `per page is the recommended pattern.`,
        element: h1s[1],
      });
    }

    // Skipped heading levels
    let lastLevel = null;
    for (const h of data.headings) {
      if (lastLevel !== null && h.level > lastLevel + 1) {
        result.findings.push({
          severity: 'medium',
          rule: 'skipped_heading_level',
          message: `Heading level jumped from h${lastLevel} to h${h.level} ` +
            `without an intervening h${lastLevel + 1}.`,
          element: h,
        });
      }
      lastLevel = h.level;
    }

    // Headings inside aside, nav, or UI components
    for (const h of data.headings) {
      if (h.insideAside) {
        result.findings.push({
          severity: 'low',
          rule: 'heading_inside_aside',
          message: `<h${h.level}> inside <aside>. Aside headings appear in ` +
            `the document outline as sub-topics of the nearest preceding ` +
            `heading, which may not be the intent.`,
          element: h,
        });
      }
      if (h.insideNav) {
        result.findings.push({
          severity: 'medium',
          rule: 'heading_inside_nav',
          message: `<h${h.level}> inside <nav>. Navigation regions should ` +
            `use aria-label or aria-labelledby on the <nav> element, not ` +
            `internal heading elements.`,
          element: h,
        });
      }
      if (h.insideUIComponent) {
        result.findings.push({
          severity: 'low',
          rule: 'heading_inside_ui_component',
          message: `<h${h.level}> inside a UI-component ancestor (class ` +
            `"${h.uiComponentClass}"). UI component titles usually should ` +
            `not be heading elements.`,
          element: h,
        });
      }
    }
  } catch (err) {
    result.findings.push({
      severity: 'high',
      rule: 'navigation_failed',
      message: err.message,
    });
  } finally {
    await context.close();
  }

  result.counts = {
    high: result.findings.filter((f) => f.severity === 'high').length,
    medium: result.findings.filter((f) => f.severity === 'medium').length,
    low: result.findings.filter((f) => f.severity === 'low').length,
  };

  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.urls.length === 0) {
    console.error(
      'Usage: node heading-hierarchy-validator.js <url> [<url> ...]'
    );
    process.exit(2);
  }

  // Launch the browser once and reuse it across URLs. A fresh context
  // per URL keeps state isolated without paying the browser launch cost
  // on every page.
  const browser = await chromium.launch();
  const results = [];
  try {
    for (const url of args.urls) {
      const result = await validateOne(url, browser);
      results.push(result);

      const status = result.counts.high === 0 ? 'OK' : 'BLOCKED';
      console.error(
        `${status}\t${result.url}\t` +
          `h=${result.counts.high} m=${result.counts.medium} l=${result.counts.low}`
      );
    }
  } finally {
    await browser.close();
  }

  console.log(
    JSON.stringify(results.length === 1 ? results[0] : results, null, 2)
  );

  const anyHigh = results.some((r) => r.counts.high > 0);
  process.exit(anyHigh ? 1 : 0);
}

main();