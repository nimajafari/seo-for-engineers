// lcp-diagnostic.test.js
//
// Unit tests for the pure parts of lcp-diagnostic.js: argument parsing,
// the four-part LCP decomposition, and exit codes. Playwright is only
// imported when the script runs, so these tests need no install step.
//
// Run:
//   node --test lcp-diagnostic.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  UsageError,
  buildReport,
  exitCode,
  lcpBreakdown,
  parseArgs,
  pickLcpResource,
  rate,
} from './lcp-diagnostic.js';

const sum = (parts) => Object.values(parts).reduce((a, b) => a + b, 0);

describe('parseArgs', () => {
  it('collects positional URLs, --urls lists, and --form-factor', () => {
    const args = parseArgs([
      '--form-factor', 'mobile', 'https://a.example/',
      '--urls', 'https://b.example/', 'https://c.example/',
    ]);
    assert.equal(args.formFactor, 'mobile');
    assert.deepEqual(args.urls, [
      'https://a.example/', 'https://b.example/', 'https://c.example/',
    ]);
  });

  it('reads --urls-file and skips comments and blank lines', () => {
    const dir = mkdtempSync(join(tmpdir(), 'lcp-'));
    const file = join(dir, 'urls.txt');
    writeFileSync(file, '# list\n\nhttps://a.example/\r\n  https://b.example/  \n');
    assert.deepEqual(parseArgs(['--urls-file', file]).urls, [
      'https://a.example/', 'https://b.example/',
    ]);
  });

  it('rejects an unknown form factor instead of silently using desktop', () => {
    assert.throws(
      () => parseArgs(['--form-factor', 'phone', 'https://a.example/']),
      UsageError,
    );
  });

  for (const argv of [
    ['--fom-factor', 'mobile', 'https://a.example/'],
    ['example.com'],
    ['--urls-file'],
    ['--urls-file', '/no/such/file.txt'],
    [],
  ]) {
    it(`rejects ${JSON.stringify(argv)}`, () => {
      assert.throws(() => parseArgs(argv), UsageError);
    });
  }
});

describe('rate', () => {
  it('uses the Core Web Vitals LCP thresholds, inclusive', () => {
    assert.equal(rate(2500), 'good');
    assert.equal(rate(2501), 'needs-improvement');
    assert.equal(rate(4000), 'needs-improvement');
    assert.equal(rate(4001), 'poor');
  });
});

describe('lcpBreakdown', () => {
  it('puts everything after TTFB into render delay for text LCP', () => {
    const { lcp, subParts } = lcpBreakdown({ lcpStartTime: 900, responseStart: 200 });
    assert.equal(lcp, 900);
    assert.deepEqual(subParts, {
      ttfb: 200, resourceLoadDelay: 0, resourceLoadDuration: 0, elementRenderDelay: 700,
    });
  });

  it('splits an image LCP into the four parts that add up to LCP', () => {
    const { lcp, subParts } = lcpBreakdown({
      lcpStartTime: 1500,
      responseStart: 300,
      resource: { startTime: 450, requestStart: 500, responseEnd: 1200 },
    });
    assert.deepEqual(subParts, {
      ttfb: 300, resourceLoadDelay: 200, resourceLoadDuration: 700, elementRenderDelay: 300,
    });
    assert.equal(sum(subParts), lcp);
  });

  it('falls back to startTime when requestStart is hidden (no Timing-Allow-Origin)', () => {
    const { subParts } = lcpBreakdown({
      lcpStartTime: 1500,
      responseStart: 300,
      resource: { startTime: 450, requestStart: 0, responseEnd: 1200 },
    });
    assert.equal(subParts.resourceLoadDelay, 150);
  });

  it('still adds up when the image was requested before TTFB (Early Hints, preload)', () => {
    const { lcp, subParts } = lcpBreakdown({
      lcpStartTime: 1000,
      responseStart: 400,
      resource: { startTime: 100, requestStart: 100, responseEnd: 600 },
    });
    assert.equal(subParts.resourceLoadDelay, 0);
    assert.equal(subParts.resourceLoadDuration, 200);
    assert.equal(sum(subParts), lcp);
  });

  it('caps the resource end at LCP (video keeps downloading after it paints)', () => {
    const { subParts } = lcpBreakdown({
      lcpStartTime: 1000,
      responseStart: 100,
      resource: { startTime: 200, requestStart: 200, responseEnd: 5000 },
    });
    assert.equal(subParts.resourceLoadDuration, 800);
    assert.equal(subParts.elementRenderDelay, 0);
  });

  it('measures from activationStart for prerendered pages', () => {
    const { lcp, subParts } = lcpBreakdown({
      lcpStartTime: 5200,
      activationStart: 5000,
      responseStart: 300,
    });
    assert.equal(lcp, 200);
    assert.equal(subParts.ttfb, 0);
    assert.equal(subParts.elementRenderDelay, 200);
  });
});

describe('pickLcpResource', () => {
  it('ignores a fetch of the same URL that started after the LCP render', () => {
    const early = { startTime: 100, requestStart: 120, responseEnd: 400 };
    const late = { startTime: 3000, requestStart: 3010, responseEnd: 3100 };
    assert.equal(pickLcpResource([early, late], 800), early);
    assert.equal(pickLcpResource([late], 800), null);
  });
});

describe('buildReport', () => {
  it('reports no_lcp_entry when the observer saw nothing', () => {
    const r = buildReport('https://a.example/', 'desktop', { lcp: null, resources: [] });
    assert.equal(r.error, 'no_lcp_entry');
  });

  it('builds a rated report with rounded sub-parts', () => {
    const r = buildReport('https://a.example/', 'mobile', {
      lcp: { startTime: 3000.4, url: 'https://a.example/hero.avif', element: { tag: 'img' } },
      resources: [{ startTime: 500, requestStart: 520.6, responseEnd: 2400.2 }],
      activationStart: 0,
      responseStart: 250.3,
      finalUrl: 'https://a.example/',
      status: 200,
    });
    assert.equal(r.rating, 'needs-improvement');
    assert.equal(r.lcp, 3000);
    assert.equal(r.lcpResourceFound, true);
    assert.deepEqual(r.subParts, {
      ttfb: 250, resourceLoadDelay: 270, resourceLoadDuration: 1880, elementRenderDelay: 600,
    });
  });
});

describe('exitCode', () => {
  it('is 0 when every URL is good', () => {
    assert.equal(exitCode([{ rating: 'good' }, { rating: 'good' }]), 0);
  });

  it('is 1 when any URL is not good, even if another failed', () => {
    assert.equal(exitCode([{ rating: 'needs-improvement' }]), 1);
    assert.equal(exitCode([{ error: 'timeout' }, { rating: 'poor' }]), 1);
  });

  it('is 2 when a URL could not be measured and none is worse than good', () => {
    assert.equal(exitCode([{ rating: 'good' }, { error: 'no_lcp_entry' }]), 2);
  });
});
