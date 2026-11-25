// cwv-rum-collector.js
//
// Production-quality RUM collector for Core Web Vitals. Uses the
// web-vitals attribution build (v6) and sends metrics to a beacon
// endpoint with segmentation by page template, device type, and
// connection type, as described in Chapter 6 of SEO for Engineers,
// Volume 1.
//
// Usage with a bundler (recommended):
//
//   npm install web-vitals
//   import './cwv-rum-collector.js';
//
// Usage without a bundler, via import map:
//
//   <script type="importmap">
//     {
//       "imports": {
//         "web-vitals/attribution":
//           "https://cdn.jsdelivr.net/npm/web-vitals@6/dist/web-vitals.attribution.js"
//       }
//     }
//   </script>
//   <script type="module" src="/cwv-rum-collector.js"></script>
//
// Configure the endpoint by editing ANALYTICS_ENDPOINT below or by
// setting window.__cwvEndpoint before this script loads.
//
// One beacon is sent per metric report. A metric can be reported more
// than once for the same page view (CLS and INP are reported again if
// they grow after the page was hidden and shown, and every bfcache
// restore starts new metric instances). Each beacon therefore carries:
//
//   id              unique per metric instance; keep the last value
//                   per id, or sum `delta` per id, never sum `value`
//   delta           change since the previous report for this id
//   navigationType  'navigate', 'reload', 'back-forward',
//                   'back-forward-cache', 'prerender', 'restore'
//
// Beacons are sent as a JSON string with a text/plain content type,
// which needs no CORS preflight; parse the body as JSON on the server.
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

import {
  onLCP, onINP, onCLS, onFCP, onTTFB,
} from 'web-vitals/attribution';

const ANALYTICS_ENDPOINT =
  (typeof window !== 'undefined' && window.__cwvEndpoint) ||
  '/analytics/web-vitals';

function getPageTemplate() {
  // Convention. Pages set <html data-template="product"> or similar.
  return (
    document.documentElement.dataset.template ||
    document.body?.dataset?.template ||
    'unknown'
  );
}

function getDeviceType() {
  const ua = navigator.userAgent || '';
  // Tablets first: iPad and Android tablet user agents also match the
  // phone patterns below. iPadOS reports a Macintosh user agent, so a
  // touch-capable "Macintosh" is treated as a tablet.
  if (
    /ipad|tablet/i.test(ua) ||
    (/android/i.test(ua) && !/mobile/i.test(ua)) ||
    (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1)
  ) {
    return 'tablet';
  }
  if (navigator.userAgentData?.mobile || /mobi/i.test(ua)) return 'mobile';
  return 'desktop';
}

function getConnectionType() {
  return navigator.connection?.effectiveType || 'unknown';
}

function send(payload) {
  const body = JSON.stringify(payload);
  try {
    // sendBeacon returns false when the browser refuses to queue the
    // beacon (for example, over its size quota); fall back to fetch.
    if (navigator.sendBeacon && navigator.sendBeacon(ANALYTICS_ENDPOINT, body)) {
      return;
    }
  } catch {
    // Fall through to fetch.
  }
  // Fetch with keepalive lets the request survive a pagehide.
  fetch(ANALYTICS_ENDPOINT, {
    method: 'POST',
    body,
    keepalive: true,
  }).catch(() => {
    // Silent. RUM should never throw into the page.
  });
}

function commonFields(metric) {
  return {
    url: location.pathname + location.search,
    pageTemplate: getPageTemplate(),
    deviceType: getDeviceType(),
    connectionType: getConnectionType(),
    timestamp: Date.now(),
    metric: metric.name,
    id: metric.id,
    navigationType: metric.navigationType || null,
    rating: metric.rating,
  };
}

// Milliseconds for timing metrics. CLS is sent as an integer scaled by
// 1000 (e.g. 0.123 -> 123) so it can be stored alongside other metric
// values without floating-point precision loss in the analytics
// backend. Matches the convention used in Chapter 6 of the book.
function scaled(metric, number) {
  return Math.round(metric.name === 'CLS' ? number * 1000 : number);
}

function valueFields(metric) {
  return { value: scaled(metric, metric.value), delta: scaled(metric, metric.delta) };
}

onLCP((metric) => {
  const { attribution } = metric;
  send({
    ...commonFields(metric),
    ...valueFields(metric),
    lcpUrl: attribution.url || null,
    lcpElement: attribution.target || null,
    ttfb: Math.round(attribution.timeToFirstByte || 0),
    resourceLoadDelay: Math.round(attribution.resourceLoadDelay || 0),
    resourceLoadDuration: Math.round(attribution.resourceLoadDuration || 0),
    elementRenderDelay: Math.round(attribution.elementRenderDelay || 0),
  });
});

onINP((metric) => {
  const { attribution } = metric;
  send({
    ...commonFields(metric),
    ...valueFields(metric),
    interactionTarget: attribution.interactionTarget || null,
    interactionType: attribution.interactionType || null,
    inputDelay: Math.round(attribution.inputDelay || 0),
    processingDuration: Math.round(attribution.processingDuration || 0),
    presentationDelay: Math.round(attribution.presentationDelay || 0),
  });
});

onCLS((metric) => {
  const { attribution } = metric;
  send({
    ...commonFields(metric),
    ...valueFields(metric),
    largestShiftTarget: attribution.largestShiftTarget || null,
    largestShiftValue: scaled(metric, attribution.largestShiftValue || 0),
  });
});

onFCP((metric) => {
  send({ ...commonFields(metric), ...valueFields(metric) });
});

onTTFB((metric) => {
  send({ ...commonFields(metric), ...valueFields(metric) });
});
