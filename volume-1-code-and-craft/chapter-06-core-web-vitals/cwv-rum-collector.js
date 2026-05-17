// cwv-rum-collector.js
//
// Production-quality RUM collector for Core Web Vitals. Uses the
// web-vitals attribution build and sends metrics to a beacon endpoint
// with segmentation by page template, device type, and connection
// type, as described in Chapter 6 of SEO for Engineers, Volume 1.
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
//           "https://cdn.jsdelivr.net/npm/web-vitals@4/dist/web-vitals.attribution.js"
//       }
//     }
//   </script>
//   <script type="module" src="/cwv-rum-collector.js"></script>
//
// Configure the endpoint by editing ANALYTICS_ENDPOINT below or by
// setting window.__cwvEndpoint before this script loads.
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
  const ua = navigator.userAgent;
  if (/mobile/i.test(ua)) return 'mobile';
  if (/tablet|ipad/i.test(ua)) return 'tablet';
  return 'desktop';
}

function getConnectionType() {
  return navigator.connection?.effectiveType || 'unknown';
}

function send(payload) {
  const body = JSON.stringify(payload);
  try {
    if (navigator.sendBeacon) {
      navigator.sendBeacon(ANALYTICS_ENDPOINT, body);
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
    headers: { 'Content-Type': 'application/json' },
  }).catch(() => {
    // Silent. RUM should never throw into the page.
  });
}

function commonFields() {
  return {
    url: location.pathname + location.search,
    pageTemplate: getPageTemplate(),
    deviceType: getDeviceType(),
    connectionType: getConnectionType(),
    timestamp: Date.now(),
  };
}

function elementSelector(el) {
  // Lightweight selector identification for attribution. Not a full
  // CSS-path resolver, just enough to identify a recurring element.
  if (!el) return null;
  if (typeof el === 'string') return el;
  const parts = [];
  parts.push(el.tagName?.toLowerCase());
  if (el.id) parts.push('#' + el.id);
  if (el.className && typeof el.className === 'string') {
    parts.push('.' + el.className.split(/\s+/).slice(0, 3).join('.'));
  }
  return parts.filter(Boolean).join('');
}

onLCP(({ value, rating, attribution }) => {
  send({
    ...commonFields(),
    metric: 'LCP',
    value: Math.round(value),
    rating,
    lcpUrl: attribution.url || null,
    lcpElement: elementSelector(attribution.element) ||
      attribution.element || null,
    ttfb: Math.round(attribution.timeToFirstByte || 0),
    resourceLoadDelay: Math.round(attribution.resourceLoadDelay || 0),
    resourceLoadDuration: Math.round(attribution.resourceLoadDuration || 0),
    elementRenderDelay: Math.round(attribution.elementRenderDelay || 0),
  });
});

onINP(({ value, rating, attribution }) => {
  send({
    ...commonFields(),
    metric: 'INP',
    value: Math.round(value),
    rating,
    interactionTarget: elementSelector(attribution.interactionTarget) ||
      attribution.interactionTarget || null,
    interactionType: attribution.interactionType || null,
    inputDelay: Math.round(attribution.inputDelay || 0),
    processingDuration: Math.round(attribution.processingDuration || 0),
    presentationDelay: Math.round(attribution.presentationDelay || 0),
  });
});

onCLS(({ value, rating, attribution }) => {
  send({
    ...commonFields(),
    metric: 'CLS',
    // Round to three decimal places, the CLS scale.
    value: Math.round(value * 1000) / 1000,
    rating,
    largestShiftTarget:
      elementSelector(attribution.largestShiftTarget) ||
      attribution.largestShiftTarget || null,
    largestShiftValue: attribution.largestShiftValue
      ? Math.round(attribution.largestShiftValue * 1000) / 1000
      : 0,
  });
});

onFCP(({ value, rating }) => {
  send({
    ...commonFields(),
    metric: 'FCP',
    value: Math.round(value),
    rating,
  });
});

onTTFB(({ value, rating }) => {
  send({
    ...commonFields(),
    metric: 'TTFB',
    value: Math.round(value),
    rating,
  });
});