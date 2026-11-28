// noindex-deployment-gate.test.js
//
// Unit tests for the pure parts of noindex-deployment-gate.js:
// argument parsing, robots directive parsing, the blocking rules, and
// exit codes. Playwright is only imported when the script runs, so
// these tests need no install step.
//
// Run:
//   node --test noindex-deployment-gate.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  UsageError,
  evaluate,
  exitCode,
  hasNoindex,
  parseArgs,
  robotsDirectives,
  statusLabel,
} from './noindex-deployment-gate.js';

const types = (observed) => evaluate(observed).map((b) => b.type);
const ok = { status: 200, xRobotsTag: [] };
const dom = (...meta) => ({ status: 200, meta });

describe('parseArgs', () => {
  it('collects URLs from positionals, --urls, and --urls-file', () => {
    const dir = mkdtempSync(join(tmpdir(), 'gate-'));
    const file = join(dir, 'urls.txt');
    writeFileSync(file, '# staging\r\nhttps://c.example/\r\n\r\n');
    const args = parseArgs(['https://a.example/', '--urls', 'https://b.example/',
      '--urls-file', file, '--settle-ms', '0']);
    assert.deepEqual(args.urls, ['https://a.example/', 'https://b.example/', 'https://c.example/']);
    assert.equal(args.settleMs, 0);
  });

  for (const argv of [
    [],
    ['--url', 'https://a.example/'],
    ['staging.example.com'],
    ['--urls-file'],
    ['--urls-file', '/no/such/file.txt'],
    ['--settle-ms', 'soon', 'https://a.example/'],
  ]) {
    it(`rejects ${JSON.stringify(argv)} as a usage error`, () => {
      assert.throws(() => parseArgs(argv), UsageError);
    });
  }
});

describe('robots directives', () => {
  for (const value of [
    'noindex', 'NOINDEX', 'none', 'index, noindex', 'noindex,nofollow',
    'noindex nofollow', 'googlebot: noindex', 'max-snippet:-1, noindex',
  ]) {
    it(`blocks ${JSON.stringify(value)}`, () => assert.equal(hasNoindex(value), true));
  }

  for (const value of [
    null, '', 'index, follow', 'nofollow', 'noimageindex',
    'max-image-preview:none', 'max-image-preview: none',
    'googlebot: max-image-preview:none', 'unavailable_after: 2026-12-31',
  ]) {
    it(`passes ${JSON.stringify(value)}`, () => assert.equal(hasNoindex(value), false));
  }

  it('scopes directives to a user-agent prefix', () => {
    assert.deepEqual(robotsDirectives('googlebot: nofollow, max-snippet:20'), [
      { agent: 'googlebot', directive: 'nofollow' },
      { agent: 'googlebot', directive: 'max-snippet' },
    ]);
  });
});

describe('evaluate', () => {
  it('passes a clean page', () => {
    assert.deepEqual(types({ http: ok, dom: dom({ name: 'robots', content: 'index, follow' }) }), []);
  });

  it('blocks noindex in any X-Robots-Tag header', () => {
    const http = { status: 200, xRobotsTag: ['max-image-preview:large', 'googlebot: noindex'] };
    const [blocker] = evaluate({ http, dom: dom() });
    assert.equal(blocker.type, 'x_robots_tag_noindex');
    assert.equal(blocker.detail, 'googlebot: noindex');
  });

  it('checks every robots and googlebot tag, not just the first', () => {
    assert.deepEqual(types({
      http: ok,
      dom: dom(
        { name: 'robots', content: 'max-snippet:-1' },
        { name: 'robots', content: 'noindex' },
        { name: 'googlebot', content: 'none' },
      ),
    }), ['meta_robots_noindex', 'meta_googlebot_noindex']);
  });

  it('does not block max-image-preview:none', () => {
    assert.deepEqual(types({
      http: { status: 200, xRobotsTag: ['max-image-preview:none'] },
      dom: dom({ name: 'robots', content: 'max-image-preview:none' }),
    }), []);
  });

  it('blocks an HTTP error status and failed checks', () => {
    assert.deepEqual(types({ http: { status: 404, xRobotsTag: [] }, dom: dom() }),
      ['http_error_status']);
    assert.deepEqual(types({ http: { error: 'ECONNREFUSED' }, dom: { error: 'net::ERR' } }),
      ['http_fetch_failed', 'page_load_failed']);
  });
});

describe('exit codes', () => {
  const result = (observed) => ({ blockers: evaluate(observed) });
  const pass = result({ http: ok, dom: dom() });
  const blocked = result({ http: ok, dom: dom({ name: 'robots', content: 'noindex' }) });
  const error = result({ http: { status: 500, xRobotsTag: [] }, dom: dom() });

  it('labels each result', () => {
    assert.deepEqual([pass, blocked, error].map(statusLabel), ['PASS', 'BLOCKED', 'ERROR']);
  });

  it('is 1 when any URL has noindex, else 2 when any could not be checked, else 0', () => {
    assert.equal(exitCode([pass, error, blocked]), 1);
    assert.equal(exitCode([pass, error]), 2);
    assert.equal(exitCode([pass, pass]), 0);
  });
});
