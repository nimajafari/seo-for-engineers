// schema-consistency-checker.js
//
// Playwright-based consistency checker for JSON-LD structured data.
// Addresses Failure Mode 4 in Chapter 9 of SEO for Engineers,
// Volume 1, the content-markup mismatch. Loads a URL, extracts the
// JSON-LD, and runs a configurable set of consistency checks
// comparing values declared in the JSON-LD against values visible in
// the rendered DOM.
//
// Default checks:
//
//   name      Product.name in JSON-LD appears in the page <h1>.
//   price     Offer.price numeric value, formatted with the declared
//             priceCurrency, appears in the visible page text.
//   stock     Offer.availability is consistent with stock-status text
//             visible on the page.
//   breadcrumb
//             Each BreadcrumbList name appears in a visible <nav>
//             landmark.
//
// Usage:
//   node schema-consistency-checker.js https://example.com/products/widget
//   node schema-consistency-checker.js --urls <url> <url>
//   node schema-consistency-checker.js <url> --checks name,price
//
// Reference: SEO for Engineers, Volume 1, Chapter 9.

import { chromium } from 'playwright';
import process from 'node:process';

const DEFAULT_CHECKS = ['name', 'price', 'stock', 'breadcrumb'];

// Schema.org availability URL to substrings that, if present in the
// visible page text, imply consistency. Case-insensitive match.
const AVAILABILITY_TEXT_SIGNALS = {
  'https://schema.org/InStock': ['in stock', 'available', 'add to cart', 'add to bag', 'buy now'],
  'https://schema.org/OutOfStock': ['out of stock', 'sold out', 'unavailable'],
  'https://schema.org/PreOrder': ['pre-order', 'preorder', 'pre order'],
  'https://schema.org/BackOrder': ['back order', 'backorder', 'backordered'],
  'https://schema.org/SoldOut': ['sold out'],
  'https://schema.org/Discontinued': ['discontinued', 'no longer available'],
  'https://schema.org/LimitedAvailability': ['limited stock', 'limited availability', 'few left'],
};

function parseArgs(argv) {
  const args = { urls: [], checks: DEFAULT_CHECKS };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--urls') {
      while (i + 1 < tokens.length && !tokens[i + 1].startsWith('--')) {
        args.urls.push(tokens[++i]);
      }
    } else if (t === '--checks') {
      args.checks = tokens[++i].split(',').map((s) => s.trim()).filter(Boolean);
    } else if (t.startsWith('http')) {
      args.urls.push(t);
    }
  }
  return args;
}

function getType(obj) {
  if (!obj || typeof obj !== 'object') return null;
  const t = obj['@type'];
  if (Array.isArray(t)) return t[0] || null;
  return typeof t === 'string' ? t : null;
}

function flatten(parsed) {
  if (Array.isArray(parsed)) {
    return parsed.flatMap(flatten);
  }
  if (parsed && typeof parsed === 'object') {
    if (Array.isArray(parsed['@graph'])) {
      return parsed['@graph'];
    }
    return [parsed];
  }
  return [];
}

function findByType(blocks, type) {
  return blocks.find((b) => getType(b) === type) || null;
}

function normalize(s) {
  return (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
}

function checkName(blocks, page, findings) {
  const product = findByType(blocks, 'Product');
  if (!product || !product.name) return;
  const declared = normalize(product.name);
  const h1Text = normalize(page.h1Text || '');
  if (!h1Text) {
    findings.push({
      severity: 'medium',
      rule: 'name_no_h1',
      message: `Product.name "${product.name}" declared, but the page has no <h1>.`,
    });
    return;
  }
  // The H1 might extend the declared name (e.g. with a model number),
  // so we allow partial match in either direction.
  if (!h1Text.includes(declared) && !declared.includes(h1Text)) {
    findings.push({
      severity: 'high',
      rule: 'name_mismatch',
      message: `Product.name "${product.name}" does not match the page <h1> "${page.h1Text}".`,
    });
  }
}

function formatPriceVariants(price, currency) {
  // Try common price formats. 1234.56, 1,234.56, 1.234,56, 1234.5, etc.
  const num = Number(price);
  if (!Number.isFinite(num)) return [];
  const fixed2 = num.toFixed(2);
  const fixed0 = String(Math.round(num));
  const withCommaThousand = fixed2.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const withDotThousand = fixed2
    .replace('.', ',')
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  const currencySymbols = {
    USD: ['$', 'US$'],
    EUR: ['€', 'EUR'],
    GBP: ['£', 'GBP'],
    JPY: ['¥', 'JPY'],
    CAD: ['CA$', 'C$', '$'],
    AUD: ['A$', '$'],
  };
  const symbols = currencySymbols[currency] || [currency];

  const variants = new Set();
  for (const numStr of [fixed2, fixed0, withCommaThousand, withDotThousand]) {
    variants.add(numStr);
    for (const sym of symbols) {
      variants.add(`${sym}${numStr}`);
      variants.add(`${sym} ${numStr}`);
      variants.add(`${numStr} ${sym}`);
      variants.add(`${numStr}${sym}`);
    }
  }
  return Array.from(variants);
}

function checkPrice(blocks, page, findings) {
  const product = findByType(blocks, 'Product');
  if (!product) return;

  let offer = null;
  if (product.offers) {
    offer = Array.isArray(product.offers) ? product.offers[0] : product.offers;
  } else {
    offer = findByType(blocks, 'Offer');
  }
  if (!offer || offer.price === undefined || !offer.priceCurrency) return;

  const variants = formatPriceVariants(offer.price, offer.priceCurrency);
  const text = (page.bodyText || '').toLowerCase();
  const found = variants.some((v) => text.includes(v.toLowerCase()));
  if (!found) {
    findings.push({
      severity: 'high',
      rule: 'price_mismatch',
      message:
        `Offer.price ${offer.price} ${offer.priceCurrency} is declared in JSON-LD ` +
        `but does not appear in the visible page text in any common ` +
        `format (tried: ${variants.slice(0, 6).join(', ')}...).`,
    });
  }
}

function checkStock(blocks, page, findings) {
  const product = findByType(blocks, 'Product');
  if (!product) return;
  let offer = null;
  if (product.offers) {
    offer = Array.isArray(product.offers) ? product.offers[0] : product.offers;
  } else {
    offer = findByType(blocks, 'Offer');
  }
  if (!offer || !offer.availability) return;

  const signals = AVAILABILITY_TEXT_SIGNALS[offer.availability];
  if (!signals) return; // Already flagged as unknown by the Python script.

  const text = (page.bodyText || '').toLowerCase();
  const found = signals.some((s) => text.includes(s));
  if (!found) {
    findings.push({
      severity: 'high',
      rule: 'stock_mismatch',
      message:
        `Offer.availability "${offer.availability}" is declared in JSON-LD ` +
        `but no consistent stock-status text appears in the visible page. ` +
        `Expected one of: ${signals.join(', ')}.`,
    });
  }

  // Also flag the inverse, an "in stock" UI signal with an OutOfStock markup.
  if (offer.availability === 'https://schema.org/OutOfStock') {
    const inStockSignals = AVAILABILITY_TEXT_SIGNALS['https://schema.org/InStock'];
    const inStockTextFound = inStockSignals.some((s) => text.includes(s));
    if (inStockTextFound) {
      findings.push({
        severity: 'high',
        rule: 'stock_conflict',
        message:
          `Offer.availability is "OutOfStock" but the page shows in-stock ` +
          `text (e.g. "in stock", "add to cart"). This is the Failure ` +
          `Mode 4 pattern.`,
      });
    }
  }
}

function checkBreadcrumb(blocks, page, findings) {
  const bl = findByType(blocks, 'BreadcrumbList');
  if (!bl || !Array.isArray(bl.itemListElement)) return;
  const navText = normalize(page.navText || '');
  if (!navText) {
    findings.push({
      severity: 'medium',
      rule: 'breadcrumb_no_nav',
      message:
        `BreadcrumbList declared in JSON-LD but no <nav> landmark text ` +
        `is visible on the page.`,
    });
    return;
  }
  for (const item of bl.itemListElement) {
    if (!item || !item.name) continue;
    const name = normalize(item.name);
    if (!navText.includes(name)) {
      findings.push({
        severity: 'medium',
        rule: 'breadcrumb_item_not_visible',
        message:
          `BreadcrumbList item "${item.name}" (position ${item.position}) ` +
          `does not appear in any <nav> on the page.`,
      });
    }
  }
}

async function checkOne(url, checks, browser) {
  const result = {
    url,
    blocks_found: 0,
    findings: [],
  };

  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 30_000 });

    const data = await page.evaluate(() => {
      const scripts = Array.from(
        document.querySelectorAll('script[type="application/ld+json"]')
      );
      const blocks = [];
      for (const s of scripts) {
        try {
          const parsed = JSON.parse(s.textContent || '');
          blocks.push(parsed);
        } catch {
          // Skip blocks that fail to parse, the Python script reports these.
        }
      }

      const h1 = document.querySelector('h1');
      const navs = Array.from(document.querySelectorAll('nav'));
      const navText = navs.map((n) => n.innerText || '').join(' ');
      // Strip <script> and <style> from bodyText.
      const body = document.body ? document.body.cloneNode(true) : null;
      if (body) {
        body.querySelectorAll('script, style, noscript').forEach((el) => el.remove());
      }
      const bodyText = body ? (body.innerText || '') : '';

      return {
        blocks,
        h1Text: h1 ? (h1.textContent || '').trim() : '',
        navText,
        bodyText,
      };
    });

    const flat = data.blocks.flatMap(flatten);
    result.blocks_found = flat.length;

    if (checks.includes('name')) checkName(flat, data, result.findings);
    if (checks.includes('price')) checkPrice(flat, data, result.findings);
    if (checks.includes('stock')) checkStock(flat, data, result.findings);
    if (checks.includes('breadcrumb')) checkBreadcrumb(flat, data, result.findings);
  } catch (err) {
    result.findings.push({
      severity: 'high',
      rule: 'page_load_failed',
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
      'Usage: node schema-consistency-checker.js <url> [<url> ...] [--checks name,price,stock,breadcrumb]'
    );
    process.exit(2);
  }

  const browser = await chromium.launch();
  const results = [];
  try {
    for (const url of args.urls) {
      const result = await checkOne(url, args.checks, browser);
      results.push(result);
      const status = result.counts.high === 0 ? 'OK' : 'FAIL';
      console.error(
        `${status}\t${result.url}\tblocks=${result.blocks_found} ` +
          `h=${result.counts.high} m=${result.counts.medium} l=${result.counts.low}`
      );
    }
  } finally {
    await browser.close();
  }

  const out = {
    results,
    summary: {
      urls_checked: results.length,
      high_severity_total: results.reduce((s, r) => s + r.counts.high, 0),
      medium_severity_total: results.reduce((s, r) => s + r.counts.medium, 0),
      low_severity_total: results.reduce((s, r) => s + r.counts.low, 0),
    },
  };
  console.log(JSON.stringify(out, null, 2));
  process.exit(out.summary.high_severity_total > 0 ? 1 : 0);
}

main();