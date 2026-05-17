// pagination-crawlability-checker.js
//
// Walk a paginated URL series and verify the conditions Chapter 10
// of SEO for Engineers, Volume 1, establishes as required for
// Google-friendly pagination.
//
// For each page in the series the script verifies:
//
//   - The page returns HTTP 200.
//   - The page has a self-referencing canonical, not a canonical
//     pointing to page 1.
//   - At least one crawlable <a href> link to a next page exists.
//   - The pagination links use real anchor elements with href, not
//     buttons or JavaScript-driven navigation.
//   - The URL does not rely on a fragment identifier (#) for the
//     page parameter.
//   - Optionally, that the page links back to page 1.
//
// Usage:
//   node pagination-crawlability-checker.js https://example.com/category/keyboards
//   node pagination-crawlability-checker.js <url> --max-pages 25
//   node pagination-crawlability-checker.js <url> --require-page-one-link
//
// Reference: SEO for Engineers, Volume 1, Chapter 10.

import { chromium } from 'playwright';
import process from 'node:process';

const DEFAULT_MAX_PAGES = 50;

function parseArgs(argv) {
  const args = {
    startUrl: null,
    maxPages: DEFAULT_MAX_PAGES,
    requirePageOneLink: false,
  };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--max-pages') {
      args.maxPages = parseInt(tokens[++i], 10) || DEFAULT_MAX_PAGES;
    } else if (t === '--require-page-one-link') {
      args.requirePageOneLink = true;
    } else if (t.startsWith('http')) {
      args.startUrl = t;
    }
  }
  return args;
}

function normalizeUrl(url) {
  try {
    const u = new URL(url);
    u.hash = '';
    return u.toString();
  } catch {
    return url;
  }
}

function urlsEquivalent(a, b) {
  return normalizeUrl(a) === normalizeUrl(b);
}

async function inspectPage(url, browser, pageOneUrl) {
  const result = {
    url,
    status: null,
    findings: [],
    canonical: null,
    nextLink: null,
    pageOneLinked: false,
    paginationLinkCount: 0,
  };

  if (url.includes('#')) {
    result.findings.push({
      severity: 'high',
      rule: 'fragment_in_url',
      message:
        `URL uses a fragment identifier (#). Google ignores everything ` +
        `after # in URLs, so this page parameter is not crawlable.`,
    });
  }

  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    const response = await page.goto(url, {
      waitUntil: 'networkidle',
      timeout: 30_000,
    });
    result.status = response ? response.status() : null;

    if (!result.status || result.status >= 400) {
      result.findings.push({
        severity: 'high',
        rule: 'non_200_status',
        message: `Page returned HTTP ${result.status}.`,
      });
      return result;
    }

    const data = await page.evaluate(() => {
      const canonical = document.querySelector('link[rel="canonical"]');

      // Collect candidate pagination links. We look at anchor elements
      // whose visible text or aria-label suggests pagination, or that
      // sit inside a <nav> with a pagination-ish label.
      const allAnchors = Array.from(document.querySelectorAll('a'));
      const paginationAnchors = allAnchors.filter((a) => {
        const href = a.getAttribute('href') || '';
        if (!href) return false;
        const text = (a.textContent || '').trim();
        const label = (a.getAttribute('aria-label') || '').toLowerCase();
        const rel = (a.getAttribute('rel') || '').toLowerCase();
        // Heuristic, true if the link looks like pagination.
        if (rel.includes('next') || rel.includes('prev')) return true;
        if (label.includes('page') || label.includes('next') || label.includes('prev')) return true;
        if (/^\d+$/.test(text)) return true; // numeric page link
        if (/^(next|prev|previous|»|‹|›|«)$/i.test(text)) return true;
        return false;
      });

      // Find a "next" link specifically.
      const next = paginationAnchors.find((a) => {
        const rel = (a.getAttribute('rel') || '').toLowerCase();
        const label = (a.getAttribute('aria-label') || '').toLowerCase();
        const text = (a.textContent || '').trim().toLowerCase();
        return (
          rel.includes('next') ||
          label.includes('next') ||
          text === 'next' ||
          text === '›' ||
          text === '»'
        );
      });

      // Also check for JS-only navigation patterns within pagination
      // containers, button[onclick], span[onclick], etc.
      const navContainers = Array.from(
        document.querySelectorAll('nav[aria-label*="agination" i], nav.pagination, [class*="pagination"]')
      );
      let jsOnlyPagination = false;
      for (const nav of navContainers) {
        const buttons = nav.querySelectorAll('button, span[role="link"], div[role="link"]');
        const anchors = nav.querySelectorAll('a[href]');
        if (buttons.length > 0 && anchors.length === 0) {
          jsOnlyPagination = true;
        }
      }

      return {
        canonical: canonical ? canonical.getAttribute('href') : null,
        paginationLinkCount: paginationAnchors.length,
        paginationHrefs: paginationAnchors
          .map((a) => a.getAttribute('href'))
          .filter(Boolean),
        nextHref: next ? next.getAttribute('href') : null,
        jsOnlyPagination,
      };
    });

    result.canonical = data.canonical;
    result.paginationLinkCount = data.paginationLinkCount;

    // Canonical check.
    if (!data.canonical) {
      result.findings.push({
        severity: 'medium',
        rule: 'no_canonical',
        message: `Page has no <link rel="canonical">.`,
      });
    } else {
      // Resolve canonical to absolute URL for comparison.
      let canonicalAbs;
      try {
        canonicalAbs = new URL(data.canonical, url).toString();
      } catch {
        canonicalAbs = data.canonical;
      }
      if (urlsEquivalent(canonicalAbs, pageOneUrl) && !urlsEquivalent(url, pageOneUrl)) {
        result.findings.push({
          severity: 'high',
          rule: 'canonical_points_to_page_one',
          message:
            `Canonical points to page 1. This is the most common pagination ` +
            `error, it prevents Google from crawling the links on deeper ` +
            `paginated pages and effectively orphans the content they link to.`,
        });
      } else if (!urlsEquivalent(canonicalAbs, url)) {
        result.findings.push({
          severity: 'medium',
          rule: 'canonical_not_self',
          message:
            `Canonical points to a URL other than this page (${canonicalAbs}). ` +
            `Paginated pages should be self-canonical.`,
        });
      }
    }

    // Pagination link check.
    if (data.paginationLinkCount === 0 && data.jsOnlyPagination) {
      result.findings.push({
        severity: 'high',
        rule: 'js_only_pagination',
        message:
          `Pagination uses buttons or JavaScript-driven elements with no ` +
          `<a href> links. Google cannot follow these.`,
      });
    } else if (data.paginationLinkCount === 0) {
      result.findings.push({
        severity: 'high',
        rule: 'no_pagination_links',
        message: `No crawlable pagination <a href> links found on this page.`,
      });
    }

    // Next-link check.
    if (data.nextHref) {
      try {
        result.nextLink = new URL(data.nextHref, url).toString();
      } catch {
        result.nextLink = data.nextHref;
      }
    }

    // Page-1 backlink check.
    const pageOneLinkPresent = data.paginationHrefs.some((href) => {
      try {
        return urlsEquivalent(new URL(href, url).toString(), pageOneUrl);
      } catch {
        return false;
      }
    });
    result.pageOneLinked = pageOneLinkPresent;
  } catch (err) {
    result.findings.push({
      severity: 'high',
      rule: 'page_load_failed',
      message: err.message,
    });
  } finally {
    await context.close();
  }

  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.startUrl) {
    console.error(
      'Usage: node pagination-crawlability-checker.js <start-url> ' +
        '[--max-pages 25] [--require-page-one-link]'
    );
    process.exit(2);
  }

  const startUrl = normalizeUrl(args.startUrl);
  const browser = await chromium.launch();
  const results = [];
  const seen = new Set();

  try {
    let currentUrl = startUrl;
    while (currentUrl && results.length < args.maxPages) {
      if (seen.has(currentUrl)) {
        console.error(`Loop detected at ${currentUrl}, stopping walk.`);
        break;
      }
      seen.add(currentUrl);

      const result = await inspectPage(currentUrl, browser, startUrl);
      results.push(result);

      // Apply the --require-page-one-link finding after the fact so it
      // shows up on every page, not just the start.
      if (
        args.requirePageOneLink &&
        !urlsEquivalent(currentUrl, startUrl) &&
        !result.pageOneLinked
      ) {
        result.findings.push({
          severity: 'medium',
          rule: 'no_page_one_backlink',
          message:
            `Page does not link back to page 1. Google's documentation ` +
            `suggests this as a hint that page 1 is the canonical landing page.`,
        });
      }

      const status =
        result.findings.filter((f) => f.severity === 'high').length === 0
          ? 'OK'
          : 'FAIL';
      console.error(
        `${status}\t${currentUrl}\tstatus=${result.status} links=${result.paginationLinkCount} ` +
          `next=${result.nextLink ? 'yes' : 'no'}`
      );

      if (!result.nextLink || urlsEquivalent(result.nextLink, currentUrl)) {
        break; // End of series.
      }
      currentUrl = normalizeUrl(result.nextLink);
    }
  } finally {
    await browser.close();
  }

  const highSeverityCount = results.reduce(
    (s, r) => s + r.findings.filter((f) => f.severity === 'high').length,
    0
  );
  const mediumSeverityCount = results.reduce(
    (s, r) => s + r.findings.filter((f) => f.severity === 'medium').length,
    0
  );

  const out = {
    start_url: startUrl,
    pages_walked: results.length,
    pages: results,
    summary: {
      high_severity_total: highSeverityCount,
      medium_severity_total: mediumSeverityCount,
    },
  };
  console.log(JSON.stringify(out, null, 2));
  process.exit(highSeverityCount > 0 ? 1 : 0);
}

main();