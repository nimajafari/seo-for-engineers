#!/usr/bin/env node
// check-robots-nodejs.mjs
//
// Validate that critical URLs remain crawlable by Googlebot, using
// the robots-parser npm package.
//
// Usage:
//   node check-robots-nodejs.mjs [path/to/robots.txt]
//
// If no path is given, defaults to public/robots.txt.
//
// Install dependency first:
//   npm install robots-parser

import { readFileSync, existsSync } from 'node:fs';
import { argv, exit } from 'node:process';
import robotsParser from 'robots-parser';

const robotsFile = argv[2] || 'public/robots.txt';

if (!existsSync(robotsFile)) {
  console.error(`FAIL: robots.txt not found at ${robotsFile}`);
  exit(1);
}

const robotsContent = readFileSync(robotsFile, 'utf8');
const robots = robotsParser(
  'https://www.example.com/robots.txt',
  robotsContent,
);

const mustBeCrawlable = [
  'https://www.example.com/',
  'https://www.example.com/products/',
  'https://www.example.com/products/category/shoes',
  'https://www.example.com/blog/',
  'https://www.example.com/sitemap.xml',
  'https://www.example.com/static/app.css',
  'https://www.example.com/static/app.js',
];

const mustBeBlocked = [
  'https://www.example.com/admin/',
  'https://www.example.com/cart',
  'https://www.example.com/account/settings',
];

let failed = 0;

for (const url of mustBeCrawlable) {
  if (!robots.isAllowed(url, 'Googlebot')) {
    console.error(`FAIL: ${url} should be crawlable by Googlebot`);
    failed++;
  }
}

for (const url of mustBeBlocked) {
  if (robots.isAllowed(url, 'Googlebot')) {
    console.error(`FAIL: ${url} should be blocked for Googlebot`);
    failed++;
  }
}

if (failed > 0) {
  console.error(`\n${failed} robots.txt check(s) failed`);
  exit(1);
}

console.log('OK: all robots.txt checks passed');