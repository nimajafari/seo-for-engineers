// dom-byte-counter.js
//
// Browser-console snippet that samples the size of document.body twice.
// Once at paste time (approximating the post-parse DOM) and once five
// seconds later (after most async work has settled). The delta tells
// you how much content arrives after the initial parse.
//
// Usage:
//   1. Load the page you want to inspect.
//   2. Open DevTools and switch to the Console tab.
//   3. Paste this entire file into the console and press Enter.
//   4. Watch the console. The first [DOM] line prints immediately. The
//      second [DOM] line prints five seconds later.
//
// Sizes are UTF-8 bytes of the serialized body. innerHTML.length would
// count UTF-16 code units instead, which undercounts every non-ASCII
// character (an accented letter is 2 bytes, most CJK characters 3).
//
// Note. Do not reload after pasting. A reload replaces the document and
// detaches anything you set up in the console, so the second sample
// would never run. Paste against the already-loaded page instead.
//
// Reference: SEO for Engineers, Volume 1, Chapter 2.

(() => {
  const encoder = new TextEncoder();
  const sample = () =>
    document.body ? encoder.encode(document.body.innerHTML).length : 0;
  const t0 = sample();
  console.log(`[DOM] At paste time: ${t0} bytes`);
  setTimeout(() => {
    const t1 = sample();
    const delta = t1 - t0;
    const sign = delta >= 0 ? '+' : '';
    console.log(`[DOM] After 5s:      ${t1} bytes (${sign}${delta})`);
  }, 5000);
  return '[DOM] measuring... second sample in 5 seconds';
})();
