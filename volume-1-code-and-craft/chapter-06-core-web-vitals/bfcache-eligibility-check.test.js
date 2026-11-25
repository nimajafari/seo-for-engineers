// bfcache-eligibility-check.test.js
//
// Unit tests for the pure parts of bfcache-eligibility-check.js: the
// Cache-Control check, how browser observations become a result, and
// exit codes. Playwright is only imported when the script runs, so
// these tests need no install step.
//
// Run:
//   node --test bfcache-eligibility-check.test.js

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

import {
  UsageError,
  classify,
  exitCode,
  flattenNotRestoredReasons,
  hasNoStore,
  parseArgs,
  statusLabel,
} from './bfcache-eligibility-check.js';

const URL = 'https://example.com/';

describe('parseArgs', () => {
  it('defaults the away page to about:blank and accepts --away', () => {
    assert.equal(parseArgs([URL]).away, 'about:blank');
    assert.equal(parseArgs(['--away', 'https://example.com/a', URL]).away,
      'https://example.com/a');
  });

  for (const argv of [['--away'], ['--bogus', URL], ['example.com'], []]) {
    it(`rejects ${JSON.stringify(argv)}`, () => {
      assert.throws(() => parseArgs(argv), UsageError);
    });
  }
});

describe('hasNoStore', () => {
  it('matches the no-store directive in any position and case', () => {
    assert.equal(hasNoStore('no-store'), true);
    assert.equal(hasNoStore('private, No-Store, max-age=0'), true);
  });

  it('does not match other directives or a missing header', () => {
    assert.equal(hasNoStore('no-cache, max-age=0'), false);
    assert.equal(hasNoStore('private, x-no-store-hint=1'), false);
    assert.equal(hasNoStore(null), false);
  });
});

describe('flattenNotRestoredReasons', () => {
  it('collects reasons from the main frame and its iframes', () => {
    const tree = {
      reasons: [{ reason: 'response-cache-control-no-store' }],
      children: [{ reasons: [{ reason: 'masked' }], children: [] }],
    };
    assert.deepEqual(flattenNotRestoredReasons(tree), [
      'response-cache-control-no-store', 'masked',
    ]);
    assert.deepEqual(flattenNotRestoredReasons(null), []);
  });
});

describe('classify', () => {
  it('a restored page without no-store is eligible', () => {
    const r = classify({ url: URL, status: 200, cacheControl: 'max-age=60', persisted: true });
    assert.equal(r.behavioralCheck, 'restored');
    assert.equal(r.eligible, true);
    assert.deepEqual(r.issues, []);
    assert.equal(statusLabel(r), 'OK');
  });

  it('a page that was not restored is never eligible', () => {
    // The original checker read navigation type "back_forward" as a
    // restore. A restored page keeps type "navigate"; "back_forward"
    // means it loaded again. Only pageshow.persisted is trusted.
    const r = classify({
      url: URL,
      persisted: false,
      notRestoredReasons: { reasons: [{ reason: 'masked' }], children: [] },
      explanations: [{ type: 'PageSupportNeeded', reason: 'WebSocket' }],
    });
    assert.equal(r.eligible, false);
    assert.equal(r.behavioralCheck, 'not_restored');
    assert.deepEqual(r.issues.map((i) => [i.type, i.severity]), [['WebSocket', 'high']]);
    assert.equal(statusLabel(r), 'BLOCKED');
  });

  it('falls back to notRestoredReasons when DevTools gives no explanation', () => {
    const r = classify({
      url: URL,
      persisted: false,
      notRestoredReasons: { reasons: [{ reason: 'unload-listener' }], children: [] },
      explanations: [],
    });
    assert.deepEqual(r.issues.map((i) => i.type), ['unload-listener']);
  });

  it('still reports a blocker when the browser gave no reason at all', () => {
    const r = classify({ url: URL, persisted: false });
    assert.deepEqual(r.issues.map((i) => i.type), ['not_restored_unknown']);
  });

  it('a no-store page is not eligible even when Chrome restored it', () => {
    const r = classify({ url: URL, cacheControl: 'no-store', persisted: true });
    assert.equal(r.restored, true);
    assert.equal(r.headerCheck, 'no_store');
    assert.equal(r.eligible, false);
    assert.deepEqual(r.issues.map((i) => i.type), ['cache_control_no_store']);
  });

  it('labels Circumstantial reasons low: they come from the environment', () => {
    const r = classify({
      url: URL,
      persisted: false,
      explanations: [{ type: 'Circumstantial', reason: 'BackForwardCacheDisabledForDelegate' }],
    });
    assert.equal(r.issues[0].severity, 'low');
  });

  it('a navigation failure is an error, not a verdict', () => {
    const r = classify({ url: URL, error: 'net::ERR_NAME_NOT_RESOLVED' });
    assert.equal(r.behavioralCheck, 'error');
    assert.equal(r.eligible, false);
    assert.equal(statusLabel(r), 'ERROR');
  });
});

describe('exitCode', () => {
  const ok = classify({ url: URL, persisted: true });
  const blocked = classify({ url: URL, persisted: false });
  const error = classify({ url: URL, error: 'timeout' });

  it('is 0 when every URL is eligible', () => {
    assert.equal(exitCode([ok, ok]), 0);
  });

  it('is 1 when any URL is blocked, even next to an error', () => {
    assert.equal(exitCode([ok, blocked]), 1);
    assert.equal(exitCode([error, blocked]), 1);
  });

  it('is 2 when a URL could not be tested and none was blocked', () => {
    assert.equal(exitCode([ok, error]), 2);
  });
});
