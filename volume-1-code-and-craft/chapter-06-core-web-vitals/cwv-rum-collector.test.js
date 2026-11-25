// cwv-rum-collector.test.js
//
// Tests for cwv-rum-collector.js. The collector is a browser module
// that imports web-vitals, so each test runs its source in a vm
// sandbox: the web-vitals import is swapped for stub on* functions
// that capture the callbacks, and the browser globals are fakes. No
// install step and no jsdom required.
//
// Run:
//   node --test cwv-rum-collector.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const SOURCE = readFileSync(new URL('./cwv-rum-collector.js', import.meta.url), 'utf-8');
const IMPORT = /import\s*\{([^}]*)\}\s*from\s*'web-vitals\/attribution';/;

const DESKTOP_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
  '(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';

function loadCollector({ userAgent = DESKTOP_UA, maxTouchPoints = 0, beaconResult = true,
  userAgentData } = {}) {
  assert.match(SOURCE, IMPORT, 'collector must import from web-vitals/attribution');
  const callbacks = {};
  const beacons = [];
  const fetches = [];
  const stub = (name) => (cb) => { callbacks[name] = cb; };
  const sandbox = {
    __webVitals: {
      onLCP: stub('LCP'), onINP: stub('INP'), onCLS: stub('CLS'),
      onFCP: stub('FCP'), onTTFB: stub('TTFB'),
    },
    window: { __cwvEndpoint: '/rum' },
    document: { documentElement: { dataset: { template: 'product' } }, body: { dataset: {} } },
    navigator: {
      userAgent,
      maxTouchPoints,
      userAgentData,
      connection: { effectiveType: '4g' },
      sendBeacon: (url, body) => {
        beacons.push({ url, body: JSON.parse(body) });
        return beaconResult;
      },
    },
    location: { pathname: '/p/widget', search: '?ref=x' },
    fetch: (url, init) => {
      fetches.push({ url, init, body: JSON.parse(init.body) });
      return Promise.resolve();
    },
  };
  vm.runInNewContext(SOURCE.replace(IMPORT, 'const {$1} = globalThis.__webVitals;'), sandbox);
  return { callbacks, beacons, fetches };
}

const lcpMetric = {
  name: 'LCP', value: 2345.6, delta: 2345.6, rating: 'good', id: 'v6-1-1',
  navigationType: 'navigate',
  attribution: {
    target: 'main > img.hero', url: 'https://cdn.example/hero.avif',
    timeToFirstByte: 300.2, resourceLoadDelay: 100.4,
    resourceLoadDuration: 1500.1, elementRenderDelay: 445.4,
  },
};

describe('cwv-rum-collector', () => {
  it('sends LCP with the v6 attribution target and the dedupe fields', () => {
    const { callbacks, beacons } = loadCollector();
    callbacks.LCP(lcpMetric);
    assert.equal(beacons.length, 1);
    const b = beacons[0];
    assert.equal(beacons[0].url, '/rum');
    assert.equal(b.body.metric, 'LCP');
    assert.equal(b.body.value, 2346);
    assert.equal(b.body.delta, 2346);
    assert.equal(b.body.id, 'v6-1-1');
    assert.equal(b.body.navigationType, 'navigate');
    assert.equal(b.body.lcpElement, 'main > img.hero');
    assert.equal(b.body.lcpUrl, 'https://cdn.example/hero.avif');
    assert.equal(b.body.pageTemplate, 'product');
    assert.equal(b.body.url, '/p/widget?ref=x');
    assert.deepEqual(
      [b.body.ttfb, b.body.resourceLoadDelay, b.body.resourceLoadDuration, b.body.elementRenderDelay],
      [300, 100, 1500, 445],
    );
  });

  it('scales CLS value, delta, and largest shift by 1000', () => {
    const { callbacks, beacons } = loadCollector();
    callbacks.CLS({
      name: 'CLS', value: 0.1234, delta: 0.0234, rating: 'needs-improvement', id: 'v6-2',
      navigationType: 'back-forward-cache',
      attribution: { largestShiftTarget: '#banner', largestShiftValue: 0.09 },
    });
    const body = beacons[0].body;
    assert.deepEqual([body.value, body.delta, body.largestShiftValue], [123, 23, 90]);
    assert.equal(body.largestShiftTarget, '#banner');
    assert.equal(body.navigationType, 'back-forward-cache');
  });

  it('sends INP phases and target', () => {
    const { callbacks, beacons } = loadCollector();
    callbacks.INP({
      name: 'INP', value: 312, delta: 312, rating: 'needs-improvement', id: 'v6-3',
      navigationType: 'navigate',
      attribution: {
        interactionTarget: 'button.add-to-cart', interactionType: 'pointer',
        inputDelay: 12.2, processingDuration: 250.4, presentationDelay: 49.6,
      },
    });
    const body = beacons[0].body;
    assert.equal(body.interactionTarget, 'button.add-to-cart');
    assert.deepEqual([body.inputDelay, body.processingDuration, body.presentationDelay],
      [12, 250, 50]);
  });

  it('falls back to fetch keepalive when sendBeacon refuses the beacon', () => {
    const { callbacks, beacons, fetches } = loadCollector({ beaconResult: false });
    callbacks.TTFB({ name: 'TTFB', value: 180, delta: 180, rating: 'good', id: 'v6-4',
      navigationType: 'navigate', attribution: {} });
    assert.equal(beacons.length, 1);
    assert.equal(fetches.length, 1);
    assert.equal(fetches[0].init.keepalive, true);
    assert.equal(fetches[0].body.metric, 'TTFB');
  });

  const deviceCases = [
    ['desktop', { userAgent: DESKTOP_UA }],
    ['mobile', { userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36' }],
    ['mobile', { userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1' }],
    ['tablet', { userAgent: 'Mozilla/5.0 (iPad; CPU OS 12_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Mobile/15E148 Safari/604.1' }],
    ['tablet', { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15', maxTouchPoints: 5 }],
    ['desktop', { userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15' }],
    ['tablet', { userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36' }],
    ['mobile', { userAgent: 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36', userAgentData: { mobile: true } }],
  ];
  for (const [expected, opts] of deviceCases) {
    it(`classifies ${opts.userAgent.slice(13, 40)}${opts.maxTouchPoints ? ' (touch)' : ''} as ${expected}`, () => {
      const { callbacks, beacons } = loadCollector(opts);
      callbacks.FCP({ name: 'FCP', value: 900, delta: 900, rating: 'good', id: 'x',
        navigationType: 'navigate', attribution: {} });
      assert.equal(beacons[0].body.deviceType, expected);
    });
  }
});
