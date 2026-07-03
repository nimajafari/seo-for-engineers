// locale-redirect-worker.example.js
//
// Reference Cloudflare Worker that handles the "first-visit locale
// redirect" pattern from Chapter 11 of SEO for Engineers, Volume 1.
// On any request to a URL without a locale prefix, the worker
// inspects Accept-Language, picks the best supported locale, and
// issues a 302 redirect to the locale-specific URL. Requests that
// already carry a locale prefix pass through unchanged.
//
// Critical design constraints, derived from the chapter:
//
//   1. The redirect must be 302, not 301. The destination varies
//      by user, so a permanent redirect would cause caches to lock
//      one locale and serve it to subsequent users.
//   2. The redirect only fires on locale-neutral URLs. Once a user
//      is on a /en/, /de/, or other locale path, content is served
//      directly with 200, regardless of Accept-Language or IP. This
//      prevents the redirect loop and locale-adaptive-page failure
//      modes described in the chapter.
//   3. Slug translation is out of scope. This worker prepends the
//      locale segment to the existing path. If your site translates
//      slugs per locale (/de/produkt vs /en/product), the variant
//      mapping must come from the CMS or database.
//
// Deploy:
//
//   - Create a Cloudflare Worker in your account.
//   - Replace the SUPPORTED_LOCALES and DEFAULT_LOCALE constants
//     with your site's actual locale set.
//   - Bind the worker to the routes that need locale detection
//     (typically `example.com/*`, excluding any static-asset paths
//     you do not want to redirect).
//
// Reference: SEO for Engineers, Volume 1, Chapter 11.

const SUPPORTED_LOCALES = ["en", "de", "fr", "es", "ja"];
const DEFAULT_LOCALE = "en";

// Paths that should never be locale-redirected. Add to taste for
// your application (static assets, health checks, API routes, etc.).
const LOCALE_NEUTRAL_PATHS = [/^\/api\//, /^\/_next\//, /^\/static\//];

function pickLocale(acceptLanguageHeader) {
  if (!acceptLanguageHeader) return DEFAULT_LOCALE;

  // Accept-Language is a comma-separated list of language tags with
  // optional q-weights, e.g. "fr-CA,fr;q=0.9,en;q=0.7". Parse to a
  // sorted list of primary-language codes.
  const candidates = acceptLanguageHeader
    .split(",")
    .map((entry) => {
      const [tag, ...params] = entry.trim().split(";");
      const q = params
        .map((p) => p.trim())
        .find((p) => p.startsWith("q="));
      const weight = q ? parseFloat(q.slice(2)) : 1.0;
      return { tag: tag.toLowerCase(), weight };
    })
    .sort((a, b) => b.weight - a.weight);

  for (const { tag } of candidates) {
    const primary = tag.split("-")[0];
    if (SUPPORTED_LOCALES.includes(primary)) {
      return primary;
    }
  }
  return DEFAULT_LOCALE;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);

    // 1. If the URL already has a locale prefix, pass through to
    //    the origin without any redirect. This is the rule that
    //    prevents redirect loops when a user navigates within the
    //    site after the first redirect.
    const localePattern = new RegExp(
      `^/(${SUPPORTED_LOCALES.join("|")})(/|$)`,
    );
    if (localePattern.test(url.pathname)) {
      return fetch(request);
    }

    // 2. If the URL matches a locale-neutral path (static asset,
    //    API route, etc.), pass through. The redirect target would
    //    be wrong for these.
    if (LOCALE_NEUTRAL_PATHS.some((re) => re.test(url.pathname))) {
      return fetch(request);
    }

    // 3. Pick the best locale from Accept-Language and 302-redirect
    //    to the corresponding locale-prefixed URL.
    const locale = pickLocale(request.headers.get("Accept-Language"));
    const redirectUrl = new URL(
      `/${locale}${url.pathname}${url.search}`,
      url.origin,
    );
    // The target depends on Accept-Language, so any shared cache must key
    // on that header. Without Vary, a CDN could cache one user's locale
    // redirect and replay it to everyone, the same cross-user locale
    // leak that constraint 1 avoids by using 302 instead of 301.
    // Response.redirect() produces an immutable response with no way to
    // add headers, so build the redirect explicitly.
    return new Response(null, {
      status: 302,
      headers: {
        Location: redirectUrl.toString(),
        Vary: "Accept-Language",
      },
    });
  },
};
