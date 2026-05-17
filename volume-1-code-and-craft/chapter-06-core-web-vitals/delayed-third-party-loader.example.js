// delayed-third-party-loader.example.js
//
// Reference implementation of the "delay non-critical third-party
// scripts" pattern described in Chapter 6 of SEO for Engineers,
// Volume 1. Defers the load of a script tag until the user either
// interacts with the page or a fallback timeout elapses, whichever
// comes first. Loads exactly once.
//
// Why this matters. Chat widgets, marketing automation scripts, and
// social share buttons rarely need to load before the user is ready to
// interact. Loading them during the initial page parse competes with
// the LCP resource for bandwidth and parser time, hurts INP by
// blocking the main thread, and contributes nothing to first-paint
// quality. Deferring them recovers all three budgets.
//
// Usage:
//
//   import { loadAfterInteractionOrTimeout } from
//     './delayed-third-party-loader.example.js';
//
//   loadAfterInteractionOrTimeout({
//     src: 'https://chat-widget.example.com/widget.js',
//   });
//
//   // Or with a non-default fallback timeout and event list.
//   loadAfterInteractionOrTimeout({
//     src: 'https://analytics.example.com/marketing.js',
//     timeoutMs: 10_000,
//     events: ['click', 'scroll', 'keydown'],
//   });
//
// The script is loaded exactly once, regardless of how many of the
// configured events fire or whether the fallback timeout also elapses.
// A user who clicks then scrolls does not trigger two script tags.
//
// Reference: SEO for Engineers, Volume 1, Chapter 6.

/**
 * Load a third-party script after the user's first interaction or
 * after a fallback timeout, whichever comes first. Idempotent.
 *
 * @param {object} options
 * @param {string} options.src                 - Script URL (required).
 * @param {number} [options.timeoutMs=5000]    - Fallback timeout in ms. 0 disables.
 * @param {string[]} [options.events]          - Interaction events that trigger load.
 * @param {boolean} [options.async=true]       - Sets `async` on the script element.
 */
export function loadAfterInteractionOrTimeout({
  src,
  timeoutMs = 5000,
  events = ['click', 'scroll', 'keydown', 'touchstart'],
  async = true,
} = {}) {
  if (typeof document === 'undefined') {
    // Server-side or non-browser environment.
    return;
  }
  if (!src) {
    throw new Error('loadAfterInteractionOrTimeout: src is required');
  }

  // The load-once flag is the load-bearing detail. Without it, a user
  // who triggers two of the configured events (click then scroll, say)
  // would cause two <script> tags to be appended, even though each
  // listener carries `once: true`. `once: true` only prevents the same
  // event from firing the same listener twice. It does not coordinate
  // across different events.
  let loaded = false;

  function load() {
    if (loaded) return;
    loaded = true;

    const script = document.createElement('script');
    script.src = src;
    script.async = async;
    document.head.appendChild(script);

    // Eagerly remove any listeners that have not yet fired so they do
    // not sit in the page's event registry for the rest of the
    // session.
    for (const event of events) {
      window.removeEventListener(event, load);
    }
  }

  for (const event of events) {
    window.addEventListener(event, load, { once: true, passive: true });
  }

  if (timeoutMs > 0) {
    setTimeout(load, timeoutMs);
  }
}
