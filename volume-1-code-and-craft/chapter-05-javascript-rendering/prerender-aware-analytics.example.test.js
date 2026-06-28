// prerender-aware-analytics.example.test.js
//
// Tests for prerender-aware-analytics.example.js. Uses Node's built-in
// test runner (node:test), available in Node 18+, so this file ships
// with no extra test-framework dependency.
//
// The module targets the browser, so the tests install a minimal fake
// `document` to drive the prerendering / prerenderingchange logic
// deterministically — no jsdom required.
//
// Run:
//   node --test prerender-aware-analytics.example.test.js
//
// The invariant the chapter argues for, and that this file enforces:
// the callback runs immediately for a real navigation, but is DEFERRED
// until prerenderingchange (and registered with { once: true }) when the
// page is being prerendered, so speculative loads never fire analytics.
//
// Reference: SEO for Engineers, Volume 1, Chapter 5.

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import { onPageActive } from './prerender-aware-analytics.example.js';

let savedDocument;
let listeners; // { type, handler, options } registered on document

// Install a fake document. `prerendering` is set per test; omit it to
// model an older browser that does not expose the property at all.
function installDocument({ prerendering } = {}) {
  listeners = [];
  const doc = {
    addEventListener: (type, handler, options) => {
      listeners.push({ type, handler, options });
    },
  };
  if (prerendering !== undefined) doc.prerendering = prerendering;
  globalThis.document = doc;
}

function fire(type) {
  for (const l of [...listeners]) {
    if (l.type === type) l.handler();
  }
}

beforeEach(() => {
  savedDocument = globalThis.document;
});

afterEach(() => {
  globalThis.document = savedDocument;
});

describe('onPageActive', () => {
  it('runs immediately for a normal navigation', () => {
    installDocument({ prerendering: false });
    const calls = [];
    onPageActive((ctx) => calls.push(ctx));

    assert.deepEqual(calls, [{ activated: false }]);
    assert.equal(listeners.length, 0, 'must not wait on any event');
  });

  it('defers until activation when the page is prerendering', () => {
    installDocument({ prerendering: true });
    const calls = [];
    onPageActive((ctx) => calls.push(ctx));

    assert.equal(calls.length, 0, 'must not fire during prerender');
    assert.equal(listeners.length, 1);
    assert.equal(listeners[0].type, 'prerenderingchange');

    fire('prerenderingchange');
    assert.deepEqual(calls, [{ activated: true }]);
  });

  it('registers the activation listener with { once: true }', () => {
    // The once flag is what makes the callback unfireable twice for a
    // single page load; the module must delegate that to the event.
    installDocument({ prerendering: true });
    onPageActive(() => {});

    assert.equal(listeners[0].options?.once, true);
  });

  it('treats a missing prerendering property as a normal navigation', () => {
    installDocument({}); // older browser: no document.prerendering
    const calls = [];
    onPageActive((ctx) => calls.push(ctx));

    assert.deepEqual(calls, [{ activated: false }]);
  });

  it('is a no-op in a non-browser environment', () => {
    globalThis.document = undefined;
    const calls = [];
    assert.doesNotThrow(() => onPageActive((ctx) => calls.push(ctx)));
    assert.equal(calls.length, 0);
  });
});
