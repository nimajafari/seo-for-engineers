// ci-validate-structured-data.example.js
//
// Reference CI integration for the structured-data validation flow
// described in Chapter 9 of SEO for Engineers, Volume 1. Fetches a
// list of URLs, extracts every <script type="application/ld+json">
// block, parses each one, and validates against per-type Ajv
// schemas plus a regression baseline that asserts which schema
// types each URL template is expected to emit.
//
// Designed to run in CI as a blocking gate. Fails the build on:
//   - Invalid JSON syntax in any JSON-LD block.
//   - Missing required Google fields per schema type.
//   - A URL template losing a structured-data type it previously had.
//
// Differences from the chapter snippet:
//   - The availability regex includes all ten Google-supported enum
//     values (the chapter snippet only listed five, which would
//     fail-close on perfectly valid SoldOut, OnlineOnly,
//     LimitedAvailability, and similar values).
//   - URL fetching is wired in so the script is runnable end to end,
//     not just a function reference.
//
// Setup:
//   npm install jsdom ajv ajv-formats node-fetch
//
// Usage:
//   node ci-validate-structured-data.example.js \\
//     --base-url http://localhost:3000 \\
//     --url /products/sample-product \\
//     --url /blog/sample-article \\
//     --url /
//
// Exit codes:
//   0 - every URL passed schema validation and regression checks.
//   1 - at least one URL failed.
//
// Reference: SEO for Engineers, Volume 1, Chapter 9.

import { JSDOM } from 'jsdom';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import process from 'node:process';

// -----------------------------------------------------------------------------
// Per-type validation schemas (subset; extend as you add types).
// -----------------------------------------------------------------------------

const productSchema = {
  type: 'object',
  required: ['@context', '@type', 'name', 'offers'],
  properties: {
    '@context': { const: 'https://schema.org' },
    '@type': { const: 'Product' },
    name: { type: 'string', minLength: 1 },
    image: {
      oneOf: [
        { type: 'string', format: 'uri' },
        {
          type: 'array',
          items: { type: 'string', format: 'uri' },
          minItems: 1,
        },
      ],
    },
    offers: {
      type: 'object',
      required: ['@type', 'price', 'priceCurrency', 'availability'],
      properties: {
        '@type': { enum: ['Offer', 'AggregateOffer'] },
        price: { type: ['number', 'string'] },
        priceCurrency: { type: 'string', pattern: '^[A-Z]{3}$' },
        // Full Google-supported availability enum. The chapter
        // snippet shipped with only the first five values, which
        // would fail-close on real-world SoldOut, OnlineOnly,
        // LimitedAvailability, etc.
        availability: {
          type: 'string',
          pattern:
            '^https://schema\\.org/' +
            '(InStock|OutOfStock|OnlineOnly|InStoreOnly|PreOrder|' +
            'PreSale|BackOrder|SoldOut|Discontinued|LimitedAvailability)$',
        },
      },
    },
    aggregateRating: {
      type: 'object',
      required: ['@type', 'ratingValue', 'reviewCount'],
      properties: {
        '@type': { const: 'AggregateRating' },
        ratingValue: { type: 'number', minimum: 1, maximum: 5 },
        reviewCount: { type: 'integer', minimum: 1 },
      },
    },
  },
};

const breadcrumbSchema = {
  type: 'object',
  required: ['@context', '@type', 'itemListElement'],
  properties: {
    '@context': { const: 'https://schema.org' },
    '@type': { const: 'BreadcrumbList' },
    itemListElement: {
      type: 'array',
      minItems: 1,
      items: {
        type: 'object',
        required: ['@type', 'position', 'name'],
        properties: {
          '@type': { const: 'ListItem' },
          position: { type: 'integer', minimum: 1 },
          name: { type: 'string', minLength: 1 },
          item: { type: 'string', format: 'uri' },
        },
      },
    },
  },
};

const VALIDATORS_BY_TYPE = {
  Product: productSchema,
  BreadcrumbList: breadcrumbSchema,
  // Extend with Article, Recipe, Event, LocalBusiness, etc.
};

// -----------------------------------------------------------------------------
// Regression baselines. Maps URL template -> expected @type values.
// -----------------------------------------------------------------------------

const REGRESSION_BASELINES = {
  '/products/:slug': ['Product', 'BreadcrumbList'],
  '/blog/:slug': ['Article', 'BreadcrumbList'],
  '/': ['Organization', 'WebSite'],
};

function matchTemplate(pathname) {
  if (pathname === '/') return '/';
  if (/^\/products\/[^/]+$/.test(pathname)) return '/products/:slug';
  if (/^\/blog\/[^/]+$/.test(pathname)) return '/blog/:slug';
  return null;
}

// -----------------------------------------------------------------------------
// Extraction
// -----------------------------------------------------------------------------

async function extractJsonLd(html) {
  const dom = new JSDOM(html);
  const scripts = dom.window.document.querySelectorAll(
    'script[type="application/ld+json"]',
  );

  const schemas = [];
  const parseErrors = [];

  scripts.forEach((script, i) => {
    const text = script.textContent || '';
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        schemas.push(...parsed);
      } else {
        schemas.push(parsed);
      }
    } catch (e) {
      parseErrors.push(`block #${i}: ${e.message}`);
    }
  });

  return { schemas, parseErrors };
}

// -----------------------------------------------------------------------------
// Validation
// -----------------------------------------------------------------------------

function validateSchemas(schemas) {
  const ajv = new Ajv({ allErrors: true, strict: false });
  addFormats(ajv);

  const errors = [];
  for (const schema of schemas) {
    const type = schema['@type'];
    const validator = VALIDATORS_BY_TYPE[type];
    if (!validator) {
      // Not a fatal CI error; just not a type we've registered a
      // strict validator for.
      continue;
    }
    const valid = ajv.validate(validator, schema);
    if (!valid) {
      errors.push({
        type,
        errors: (ajv.errors || []).map(
          (e) => `${e.instancePath || '<root>'} ${e.message}`,
        ),
      });
    }
  }
  return errors;
}

function checkForRegressions(pathname, schemas) {
  const template = matchTemplate(pathname);
  if (!template) return null;
  const expectedTypes = REGRESSION_BASELINES[template];
  if (!expectedTypes) return null;
  const actualTypes = schemas.map((s) => s['@type']);
  const missing = expectedTypes.filter((t) => !actualTypes.includes(t));
  return missing.length ? { template, missing } : null;
}

// -----------------------------------------------------------------------------
// CLI
// -----------------------------------------------------------------------------

function parseArgs(argv) {
  const args = { baseUrl: 'http://localhost:3000', urls: [] };
  const tokens = argv.slice(2);
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i] === '--base-url') args.baseUrl = tokens[++i];
    else if (tokens[i] === '--url') args.urls.push(tokens[++i]);
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.urls.length) {
    console.error(
      'Usage: node ci-validate-structured-data.example.js ' +
        '--base-url http://localhost:3000 --url /products/sample [--url /...]',
    );
    process.exit(2);
  }

  let failures = 0;

  for (const path of args.urls) {
    const fullUrl = args.baseUrl + path;
    let html;
    try {
      const response = await fetch(fullUrl);
      if (!response.ok) {
        console.error(`FAIL ${fullUrl} -> HTTP ${response.status}`);
        failures++;
        continue;
      }
      html = await response.text();
    } catch (err) {
      console.error(`FAIL ${fullUrl} -> ${err.message}`);
      failures++;
      continue;
    }

    const { schemas, parseErrors } = await extractJsonLd(html);
    if (parseErrors.length) {
      console.error(`FAIL ${fullUrl} -> JSON parse errors:`);
      parseErrors.forEach((e) => console.error(`  ${e}`));
      failures++;
      continue;
    }

    const schemaErrors = validateSchemas(schemas);
    if (schemaErrors.length) {
      console.error(`FAIL ${fullUrl} -> schema validation:`);
      for (const { type, errors } of schemaErrors) {
        console.error(`  ${type}:`);
        errors.forEach((e) => console.error(`    ${e}`));
      }
      failures++;
      continue;
    }

    const regression = checkForRegressions(path, schemas);
    if (regression) {
      console.error(
        `FAIL ${fullUrl} -> regression on template ${regression.template}: ` +
          `missing ${regression.missing.join(', ')}`,
      );
      failures++;
      continue;
    }

    const types = schemas.map((s) => s['@type']).join(', ') || '<none>';
    console.log(`OK   ${fullUrl} -> [${types}]`);
  }

  if (failures > 0) {
    console.error(`\n${failures} URL(s) failed structured-data validation.`);
    process.exit(1);
  }
  console.log(`\nAll ${args.urls.length} URL(s) passed.`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
