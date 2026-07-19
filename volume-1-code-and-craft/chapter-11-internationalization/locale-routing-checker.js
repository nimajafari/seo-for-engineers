// locale-routing-checker.js
//
// Verify that locale URLs serve their content directly with a 200
// status and are not locale-adaptive, the foundational rule Chapter
// 11 of SEO for Engineers, Volume 1, establishes for multilingual
// SEO.
//
// For each URL the script verifies:
//
//   - The page returns HTTP 200 with no redirects.
//   - The page returns the same 200 response for at least three
//     different Accept-Language headers (proving the response is not
//     header-adaptive).
//   - The rendered <html lang> attribute matches the declared locale.
//   - The page has a self-referencing rel="canonical".
//   - The page has a self-referencing hreflang annotation.
//
// Usage:
//   node locale-routing-checker.js --url <url> --locale <locale>
//   node locale-routing-checker.js --urls urls.json
//
// Reference: SEO for Engineers, Volume 1, Chapter 11.

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import process from 'node:process';

// The three Accept-Language probes. The first is a control, the
// second is intentionally conflicting, the third matches.
const PROBE_HEADERS = [
  { label: 'control_en', acceptLanguage: 'en-US,en;q=0.9' },
  { label: 'conflicting_de', acceptLanguage: 'de-DE,de;q=0.9' },
  { label: 'conflicting_ja', acceptLanguage: 'ja-JP,ja;q=0.9' },
];

function parseArgs(argv) {
  const args = { url: null, locale: null, urlsFile: null };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (t === '--url') args.url = tokens[++i];
    else if (t === '--locale') args.locale = tokens[++i];
    else if (t === '--urls') args.urlsFile = tokens[++i];
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

async function probeOnce(browser, url, acceptLanguage) {
  const context = await browser.newContext({
    extraHTTPHeaders: { 'Accept-Language': acceptLanguage },
  });
  const page = await context.newPage();
  const redirectChain = [];

  page.on('response', (response) => {
    if (response.status() >= 300 && response.status() < 400) {
      redirectChain.push({
        from: response.url(),
        status: response.status(),
        to: response.headers().location,
      });
    }
  });

  try {
    const response = await page.goto(url, {
      waitUntil: 'networkidle',
      timeout: 30_000,
    });
    const finalUrl = page.url();
    const status = response ? response.status() : null;

    const dom = await page.evaluate(() => {
      const htmlLang = document.documentElement.getAttribute('lang') || '';
      const canonical = document.querySelector('link[rel="canonical"]');
      const hreflangs = Array.from(
        document.querySelectorAll('link[rel="alternate"][hreflang]')
      ).map((el) => ({
        hreflang: el.getAttribute('hreflang') || '',
        href: el.getAttribute('href') || '',
      }));
      const title = document.title || '';
      const h1 = document.querySelector('h1');
      const h1Text = h1 ? (h1.textContent || '').trim().slice(0, 200) : '';
      return {
        htmlLang,
        canonical: canonical ? canonical.getAttribute('href') : null,
        hreflangs,
        title,
        h1Text,
      };
    });

    return {
      acceptLanguage,
      status,
      requestUrl: url,
      finalUrl,
      redirected: finalUrl !== url,
      redirectChain,
      ...dom,
    };
  } finally {
    await context.close();
  }
}

function urlsEquivalent(a, b) {
  if (!a || !b) return false;
  try {
    const ua = new URL(a);
    const ub = new URL(b);
    ua.hash = '';
    ub.hash = '';
    return ua.toString() === ub.toString();
  } catch {
    return a === b;
  }
}

async function inspectUrl(browser, target) {
  const result = {
    url: target.url,
    locale: target.locale,
    findings: [],
    probes: [],
  };

  // Probe the URL with three different Accept-Language headers.
  for (const probe of PROBE_HEADERS) {
    try {
      const probeResult = await probeOnce(
        browser,
        target.url,
        probe.acceptLanguage
      );
      result.probes.push({ label: probe.label, ...probeResult });
    } catch (err) {
      result.findings.push({
        severity: 'high',
        rule: 'probe_failed',
        message: `Probe ${probe.label} failed, ${err.message}`,
      });
    }
  }

  if (result.probes.length === 0) return result;

  // Check 1, no redirects on any probe.
  for (const probe of result.probes) {
    if (probe.redirected || probe.redirectChain.length > 0) {
      result.findings.push({
        severity: 'high',
        rule: 'locale_url_redirects',
        message: (
          `Locale URL redirected under Accept-Language=${probe.acceptLanguage}. ` +
          `${probe.requestUrl} -> ${probe.finalUrl}. ` +
          `Locale URLs must serve content directly with 200.`
        ),
      });
    }
    if (probe.status !== 200) {
      result.findings.push({
        severity: 'high',
        rule: 'non_200_status',
        message: (
          `Locale URL returned HTTP ${probe.status} under ` +
          `Accept-Language=${probe.acceptLanguage}.`
        ),
      });
    }
  }

  // Check 2, response not locale-adaptive across probes.
  const ref = result.probes[0];
  for (let i = 1; i < result.probes.length; i++) {
    const p = result.probes[i];
    if (p.htmlLang && ref.htmlLang && p.htmlLang !== ref.htmlLang) {
      result.findings.push({
        severity: 'high',
        rule: 'locale_adaptive_content',
        message: (
          `Response varies by Accept-Language. <html lang> was ` +
          `'${ref.htmlLang}' under ${ref.acceptLanguage} but ` +
          `'${p.htmlLang}' under ${p.acceptLanguage}. The same URL is ` +
          `serving different locales based on request headers, which ` +
          `breaks crawlability.`
        ),
      });
    }
    if (p.title && ref.title && p.title !== ref.title) {
      result.findings.push({
        severity: 'high',
        rule: 'title_varies_by_accept_language',
        message: (
          `Page <title> varies by Accept-Language. '${ref.title}' under ` +
          `${ref.acceptLanguage}, '${p.title}' under ${p.acceptLanguage}.`
        ),
      });
    }
    if (p.h1Text && ref.h1Text && p.h1Text !== ref.h1Text) {
      result.findings.push({
        severity: 'medium',
        rule: 'h1_varies_by_accept_language',
        message: (
          `<h1> content varies by Accept-Language under the same URL.`
        ),
      });
    }
  }

  // Check 3, <html lang> matches the URL-declared locale.
  if (target.locale && ref.htmlLang) {
    const declaredLang = target.locale.toLowerCase();
    const pageLang = ref.htmlLang.toLowerCase();
    // Match if either is a prefix of the other (e.g. 'de' matches 'de-de').
    const matches =
      pageLang === declaredLang ||
      pageLang.startsWith(declaredLang + '-') ||
      declaredLang.startsWith(pageLang + '-');
    if (!matches) {
      result.findings.push({
        severity: 'medium',
        rule: 'html_lang_mismatch',
        message: (
          `URL declares locale '${target.locale}' but <html lang> is ` +
          `'${ref.htmlLang}'.`
        ),
      });
    }
  }

  // Check 4, self-referencing canonical.
  if (ref.canonical) {
    let canonicalAbs;
    try {
      canonicalAbs = new URL(ref.canonical, target.url).toString();
    } catch {
      canonicalAbs = ref.canonical;
    }
    if (!urlsEquivalent(canonicalAbs, target.url)) {
      result.findings.push({
        severity: 'high',
        rule: 'canonical_not_self',
        message: (
          `Canonical does not self-reference. URL is ${target.url}, ` +
          `canonical points to ${canonicalAbs}. Locale pages must be ` +
          `self-canonical.`
        ),
      });
    }
  } else {
    result.findings.push({
      severity: 'medium',
      rule: 'no_canonical',
      message: 'Page has no <link rel="canonical">.',
    });
  }

  // Check 5, self-referencing hreflang.
  if (ref.hreflangs && ref.hreflangs.length > 0) {
    const hasSelf = ref.hreflangs.some((h) => {
      try {
        return urlsEquivalent(new URL(h.href, target.url).toString(), target.url);
      } catch {
        return false;
      }
    });
    if (!hasSelf) {
      result.findings.push({
        severity: 'high',
        rule: 'no_self_hreflang',
        message: (
          `Page has hreflang annotations but none point to itself. ` +
          `Self-reference is required.`
        ),
      });
    }
  } else {
    result.findings.push({
      severity: 'medium',
      rule: 'no_hreflang_annotations',
      message: 'Page has no hreflang annotations.',
    });
  }

  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  let targets = [];

  if (args.urlsFile) {
    let content;
    try {
      content = readFileSync(args.urlsFile, 'utf-8');
    } catch (err) {
      console.error(`Cannot read --urls file '${args.urlsFile}': ${err.message}`);
      process.exit(2);
    }
    try {
      targets = JSON.parse(content);
    } catch (err) {
      console.error(
        `--urls file '${args.urlsFile}' is not valid JSON: ${err.message}`
      );
      process.exit(2);
    }
    if (!Array.isArray(targets)) {
      console.error(
        `--urls file '${args.urlsFile}' must contain a JSON array of ` +
          `{ "url": ..., "locale": ... } objects.`
      );
      process.exit(2);
    }
  } else if (args.url) {
    targets = [{ url: args.url, locale: args.locale || null }];
  } else {
    console.error(
      'Usage: node locale-routing-checker.js --url <url> --locale <locale>\n' +
        '       node locale-routing-checker.js --urls urls.json'
    );
    process.exit(2);
  }

  targets = targets.map((t) => ({ ...t, url: normalizeUrl(t.url) }));

  const browser = await chromium.launch();
  const results = [];

  try {
    for (const target of targets) {
      console.error(`Probing ${target.url} (locale=${target.locale})...`);
      const result = await inspectUrl(browser, target);
      results.push(result);

      const highCount = result.findings.filter(
        (f) => f.severity === 'high'
      ).length;
      const tag = highCount === 0 ? 'OK' : 'FAIL';
      console.error(
        `${tag}  ${target.url}  high=${highCount} ` +
          `med=${result.findings.filter((f) => f.severity === 'medium').length}`
      );
    }
  } finally {
    await browser.close();
  }

  const highTotal = results.reduce(
    (s, r) => s + r.findings.filter((f) => f.severity === 'high').length,
    0
  );
  const mediumTotal = results.reduce(
    (s, r) => s + r.findings.filter((f) => f.severity === 'medium').length,
    0
  );

  const out = {
    urls_checked: results.length,
    results,
    summary: {
      high_severity_total: highTotal,
      medium_severity_total: mediumTotal,
    },
  };
  console.log(JSON.stringify(out, null, 2));
  process.exit(highTotal > 0 ? 1 : 0);
}

main();