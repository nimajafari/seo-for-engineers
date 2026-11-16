// dom-byte-counter.test.js
//
// Runs the console snippet in a sandbox with a fake document, console,
// and setTimeout, so it can be tested under node:test with no browser.

'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(path.join(__dirname, 'dom-byte-counter.js'), 'utf8');

function runSnippet(initialHtml) {
  const logs = [];
  let deferred = null;
  const document = { body: initialHtml === null ? null : { innerHTML: initialHtml } };
  const context = vm.createContext({
    document,
    TextEncoder,
    console: { log: (msg) => logs.push(msg) },
    setTimeout: (fn, ms) => {
      deferred = { fn, ms };
    },
  });
  const returned = vm.runInContext(SOURCE, context);
  return { logs, deferred, document, returned };
}

test('reports UTF-8 bytes, not UTF-16 code units', () => {
  // "é" is 2 bytes and "東" is 3 bytes in UTF-8, but 1 code unit each.
  const { logs } = runSnippet('é東');
  assert.match(logs[0], /At paste time: 5 bytes/);
});

test('second sample runs after 5s and reports the delta', () => {
  const { logs, deferred, document } = runSnippet('<p>a</p>');
  assert.strictEqual(deferred.ms, 5000);
  document.body.innerHTML = '<p>a</p><p>injected</p>';
  deferred.fn();
  assert.match(logs[1], /After 5s: +23 bytes \(\+15\)/);
});

test('negative delta keeps its sign', () => {
  const { logs, deferred, document } = runSnippet('<p>long content</p>');
  document.body.innerHTML = '';
  deferred.fn();
  assert.match(logs[1], /\(-19\)/);
});

test('missing body counts as zero', () => {
  const { logs } = runSnippet(null);
  assert.match(logs[0], /At paste time: 0 bytes/);
});

test('returns a status string for the console', () => {
  const { returned } = runSnippet('');
  assert.match(returned, /measuring/);
});
