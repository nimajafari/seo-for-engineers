// prerender-aware-analytics.example.js
//
// Reference implementation of the prerender-aware analytics pattern
// described in Chapter 5 of SEO for Engineers, Volume 1. Defers
// analytics initialization until the page is the user's actual
// navigation, not a speculative prerender from the Speculation Rules
// API.
//
// Why this matters. When Chromium prerenders a page under the
// Speculation Rules API, it executes the full page lifecycle in a
// hidden browsing context. JavaScript runs, event listeners fire, and
// load events fire, all before the user has navigated. If your
// analytics fires a pageview on load, the prerender inflates pageview
// counts with sessions the user never consciously initiated.
//
// The fix. Check document.prerendering at startup. If true, defer
// analytics initialization to the prerenderingchange event, which
// fires when the user actually navigates to the prerendered page. If
// false, run analytics immediately as normal.
//
// Usage:
//
//   import { onPageActive } from './prerender-aware-analytics.example.js';
//
//   onPageActive(({ activated }) => {
//     initializeAnalytics();
//     firePageviewEvent();
//     if (activated) {
//       // Optional, log that this load arrived via prerender
//       // activation. Useful for measuring speculation-rules impact
//       // separately from normal navigations.
//     }
//   });
//
// The callback fires exactly once per page load:
//   - Immediately, if the page was loaded by a real navigation.
//   - After prerenderingchange, if the page was prerendered and is
//     now being activated by the user.
//
// Pages that are prerendered but never activated (the user navigates
// somewhere else) will not run the callback. That is the intended
// behavior. Speculative loads should not inflate pageview counts,
// fire conversion pixels, or assign A/B variants.
//
// Pair this with the server-side Sec-Purpose middleware described in
// Chapter 5 to suppress side effects across the full request path.
//
// Reference: SEO for Engineers, Volume 1, Chapter 5.

/**
 * Run a callback once the page is the user's active navigation.
 *
 * @param {(context: { activated: boolean }) => void} callback
 *   Invoked once with `{ activated: false }` for a normal navigation,
 *   or `{ activated: true }` when a prerendered page is activated.
 */
export function onPageActive(callback) {
  if (typeof document === 'undefined') {
    // Server-side or non-browser environment. No-op.
    return;
  }

  // document.prerendering is true only while the page is being
  // prerendered. Older browsers do not expose the property at all,
  // which is the same observable shape as a normal navigation.
  if (!document.prerendering) {
    callback({ activated: false });
    return;
  }

  // Defer until the prerender is activated. `once: true` makes the
  // callback unfireable twice for the same page load.
  document.addEventListener(
    'prerenderingchange',
    () => callback({ activated: true }),
    { once: true }
  );
}
