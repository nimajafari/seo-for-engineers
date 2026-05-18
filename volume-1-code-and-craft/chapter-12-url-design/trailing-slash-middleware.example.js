// trailing-slash-middleware.example.js
//
// Express middleware that enforces the no-trailing-slash convention
// described in Chapter 12 of SEO for Engineers, Volume 1. Any
// request whose path ends with `/` (other than the root `/` itself)
// is 301-redirected to the same URL with the trailing slash removed.
// Query strings and fragments are preserved.
//
// The 301 (permanent) is intentional. A 302 (temporary) would tell
// search engines to keep both URL variants in the index, which is
// the opposite of what trailing-slash normalization is meant to
// accomplish.
//
// Apply this middleware as early as possible in the request
// pipeline, before routing and before any handlers that might
// match either form of the URL:
//
//   const express = require("express");
//   const { stripTrailingSlash } = require("./trailing-slash-middleware.example");
//
//   const app = express();
//   app.use(stripTrailingSlash);
//   // ... routes
//
// If your site uses the opposite convention (trailing slashes
// required), this middleware should not be used. Instead, redirect
// the no-slash form to the slash form, and make sure your server
// is configured to do that ONCE, at a single layer (either app
// middleware OR CDN, not both — which is the source of failure
// mode 3 in the chapter).
//
// Reference: SEO for Engineers, Volume 1, Chapter 12.

/**
 * Strip trailing slashes from non-root paths via 301 redirect.
 *
 * @param {import("express").Request} req
 * @param {import("express").Response} res
 * @param {import("express").NextFunction} next
 */
function stripTrailingSlash(req, res, next) {
  // The path is everything before `?` in the URL, without the
  // query string. We compare against req.path (Express-normalized)
  // and reconstruct the redirect target with req.url to preserve
  // the query string.
  if (req.path === "/" || !req.path.endsWith("/")) {
    return next();
  }

  // Reconstruct the path-without-trailing-slash plus query string.
  const newPath = req.path.slice(0, -1);
  const querySuffix = req.url.slice(req.path.length);
  res.redirect(301, newPath + querySuffix);
}

module.exports = { stripTrailingSlash };
