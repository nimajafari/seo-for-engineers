// heading-hierarchy-validator.test.js
//
// Unit tests for the pure parts of heading-hierarchy-validator.js:
// argument parsing, the heading rules, UI-component detection, and
// exit codes. Playwright is only imported when the script runs, so
// these tests need no install step.
//
// Run:
//   node --test heading-hierarchy-validator.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  UsageError,
  countFindings,
  evaluateHeadings,
  exitCode,
  findUiComponent,
  parseArgs,
  statusLabel,
} from './heading-hierarchy-validator.js';

// A collected heading as collectHeadings() returns it from the page.
const h = (level, ancestors = [], extra = {}) => ({
  level,
  text: `Heading ${level}`,
  id: null,
  className: null,
  inShadowDom: false,
  ancestors,
  ...extra,
});
const el = (tag, className = null, role = null) => ({ tag, className, role });
const rules = (collected) => evaluateHeadings(collected).findings.map((f) => f.rule);

describe('parseArgs', () => {
  it('collects URLs and --settle-ms', () => {
    const args = parseArgs(['--settle-ms', '2000', 'https://a.example/',
      '--urls', 'https://b.example/']);
    assert.equal(args.settleMs, 2000);
    assert.deepEqual(args.urls, ['https://a.example/', 'https://b.example/']);
  });

  for (const argv of [
    ['--url', 'https://a.example/'],
    ['--settle-ms', 'soon', 'https://a.example/'],
    ['a.example'],
    ['--urls-file', '/no/such/file.txt'],
    [],
  ]) {
    it(`rejects ${JSON.stringify(argv)}`, () => {
      assert.throws(() => parseArgs(argv), UsageError);
    });
  }
});

describe('evaluateHeadings', () => {
  it('passes a clean outline', () => {
    assert.deepEqual(rules([h(1), h(2), h(3), h(2)]), []);
  });

  it('flags a missing and a duplicate h1', () => {
    assert.deepEqual(rules([h(2)]), ['missing_h1']);
    assert.deepEqual(rules([h(1), h(2), h(1)]), ['multiple_h1']);
  });

  it('flags each skipped level, but not a jump back up', () => {
    assert.deepEqual(rules([h(1), h(3), h(2), h(5)]),
      ['skipped_heading_level', 'skipped_heading_level']);
    assert.deepEqual(rules([h(1), h(2), h(3), h(4), h(2)]), []);
  });

  it('counts a second h1 from a shadow root', () => {
    const { headings, findings } = evaluateHeadings([
      h(1), h(1, [el('product-card')], { inShadowDom: true }),
    ]);
    assert.equal(headings[1].inShadowDom, true);
    assert.equal(findings[0].rule, 'multiple_h1');
  });

  it('flags headings inside aside, nav, and UI components', () => {
    assert.deepEqual(rules([
      h(1),
      h(2, [el('div'), el('aside')]),
      h(2, [el('nav')]),
      h(2, [el('div', 'product-card__body'), el('section')]),
    ]), ['heading_inside_aside', 'heading_inside_nav', 'heading_inside_ui_component']);
  });

  it('names the UI component by class, or by role when it has none', () => {
    const { headings } = evaluateHeadings([
      h(1),
      h(2, [el('div', null, 'dialog')]),
    ]);
    assert.equal(headings[1].uiComponentClass, '[role=dialog]');
  });
});

describe('findUiComponent', () => {
  it('returns the nearest matching ancestor', () => {
    const near = el('div', 'Modal-content');
    assert.equal(findUiComponent([el('div', 'body'), near, el('div', 'card')]), near);
  });

  it('ignores ancestors that do not match', () => {
    assert.equal(findUiComponent([el('section', 'content'), el('main')]), null);
  });
});

describe('exit codes', () => {
  const ok = { counts: countFindings([]) };
  const blocked = { counts: countFindings([{ severity: 'high' }]) };
  const error = { error: 'HTTP 404', counts: countFindings([]) };

  it('labels each result', () => {
    assert.deepEqual([ok, blocked, error].map(statusLabel), ['OK', 'BLOCKED', 'ERROR']);
  });

  it('is 1 when any URL is blocked, else 2 when any errored, else 0', () => {
    assert.equal(exitCode([ok, blocked, error]), 1);
    assert.equal(exitCode([ok, error]), 2);
    assert.equal(exitCode([ok, ok]), 0);
  });
});
