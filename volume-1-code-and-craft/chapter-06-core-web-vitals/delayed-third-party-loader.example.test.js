// delayed-third-party-loader.example.test.js
//
// Tests for delayed-third-party-loader.example.js. Uses Node's built-in
// test runner (node:test), available in Node 18+, so this file ships
// with no extra test-framework dependency.
//
// The module targets the browser, so the tests install minimal fake
// `window`, `document`, and `setTimeout` globals to drive it
// deterministically — no jsdom required.
//
// Run:
//   node --test delayed-third-party-loader.example.test.js
//
// The load-bearing invariant the chapter argues for, and that this file
// enforces: the script loads EXACTLY ONCE, no matter how many of the
// configured interaction events fire or whether the fallback timeout
// also elapses.
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import { describe, it, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

import { loadAfterInteractionOrTimeout } from './delayed-third-party-loader.example.js';

// Captures of original globals so each test restores a clean slate.
let savedDocument;
let savedWindow;
let savedSetTimeout;

// Per-test harness state.
let scripts; // <script> elements appended to <head>
let listeners; // { type, handler } registered on window
let timers; // captured setTimeout callbacks (not actually scheduled)

function installBrowserStubs() {
  scripts = [];
  listeners = [];
  timers = [];

  globalThis.document = {
    createElement: (tag) => ({ tagName: tag, src: null, async: undefined }),
    head: {
      appendChild: (el) => {
        scripts.push(el);
      },
    },
  };

  globalThis.window = {
    addEventListener: (type, handler, options) => {
      listeners.push({ type, handler, options });
    },
    removeEventListener: (type, handler) => {
      const i = listeners.findIndex(
        (l) => l.type === type && l.handler === handler,
      );
      if (i >= 0) listeners.splice(i, 1);
    },
  };

  // Capture timers instead of scheduling them, so the fallback path is
  // driven explicitly and tests stay synchronous.
  globalThis.setTimeout = (fn, ms) => {
    timers.push({ fn, ms });
    return timers.length;
  };
}

// Simulate one of the registered interaction events firing.
function fireEvent(type) {
  for (const l of [...listeners]) {
    if (l.type === type) l.handler();
  }
}

beforeEach(() => {
  savedDocument = globalThis.document;
  savedWindow = globalThis.window;
  savedSetTimeout = globalThis.setTimeout;
  installBrowserStubs();
});

afterEach(() => {
  globalThis.document = savedDocument;
  globalThis.window = savedWindow;
  globalThis.setTimeout = savedSetTimeout;
});

describe('loadAfterInteractionOrTimeout', () => {
  it('loads the script on the first interaction', () => {
    loadAfterInteractionOrTimeout({ src: 'https://w.example/widget.js', timeoutMs: 0 });
    assert.equal(scripts.length, 0, 'must not load before any interaction');

    fireEvent('click');
    assert.equal(scripts.length, 1);
    assert.equal(scripts[0].src, 'https://w.example/widget.js');
  });

  it('loads exactly once across two different events', () => {
    loadAfterInteractionOrTimeout({
      src: 'https://w.example/widget.js',
      timeoutMs: 0,
      events: ['click', 'scroll'],
    });

    fireEvent('click');
    fireEvent('scroll'); // second, different event must not load again
    assert.equal(scripts.length, 1, 'click-then-scroll must yield one script');
  });

  it('loads exactly once when an interaction and the timeout both fire', () => {
    loadAfterInteractionOrTimeout({ src: 'https://w.example/widget.js', timeoutMs: 5000 });

    fireEvent('click');
    assert.equal(timers.length, 1, 'a fallback timer should be registered');
    timers[0].fn(); // fallback elapses after the interaction already loaded
    assert.equal(scripts.length, 1);
  });

  it('falls back to the timeout when no interaction occurs', () => {
    loadAfterInteractionOrTimeout({ src: 'https://w.example/widget.js', timeoutMs: 5000 });
    assert.equal(scripts.length, 0);

    timers[0].fn();
    assert.equal(scripts.length, 1);
  });

  it('removes pending listeners once loaded', () => {
    loadAfterInteractionOrTimeout({
      src: 'https://w.example/widget.js',
      timeoutMs: 0,
      events: ['click', 'scroll', 'keydown'],
    });
    assert.equal(listeners.length, 3);

    fireEvent('click');
    assert.equal(listeners.length, 0, 'all interaction listeners cleaned up');
  });

  it('sets async on the injected script element', () => {
    loadAfterInteractionOrTimeout({ src: 'https://w.example/a.js', timeoutMs: 0 });
    fireEvent('click');
    assert.equal(scripts[0].async, true);

    installBrowserStubs(); // fresh state for the async:false case
    loadAfterInteractionOrTimeout({ src: 'https://w.example/b.js', timeoutMs: 0, async: false });
    fireEvent('click');
    assert.equal(scripts[0].async, false);
  });

  it('throws when src is missing', () => {
    assert.throws(() => loadAfterInteractionOrTimeout({}), /src is required/);
  });

  it('is a no-op in a non-browser environment', () => {
    globalThis.document = undefined;
    assert.doesNotThrow(() =>
      loadAfterInteractionOrTimeout({ src: 'https://w.example/widget.js' }),
    );
  });
});
