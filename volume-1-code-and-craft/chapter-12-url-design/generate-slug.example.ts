// generate-slug.example.ts
//
// TypeScript port of the slug generator from Chapter 12 of SEO for
// Engineers, Volume 1. The Python reference implementation lives at
// example_slug_implementation.py in this same directory; this file
// is the equivalent algorithm for Node.js / TypeScript backends.
//
// The API matches the Python version function-for-function:
//
//   - Unicode NFKD normalization + diacritic stripping for ASCII
//     output. For non-Latin scripts, see the note below.
//   - Lowercase, non-alphanumeric -> hyphen, collapse hyphens, trim.
//   - Word-boundary-aware truncation to maxLength.
//   - Reserved-word protection against routing conflicts.
//   - Collision resolution via an async existsFn callback.
//   - Shared counter between reserved-word and collision resolution
//     so a slug that hits both keeps incrementing rather than
//     restarting.
//
// Non-Latin input. The NFKD + diacritic-stripping approach
// produces an empty string for input that contains no Latin
// characters (Japanese, Chinese, Cyrillic, Arabic, etc.). For
// multilingual sites, either:
//   - Transliterate first with a library like `transliteration`
//     and pass the result into generateSlug, OR
//   - Use the FALLBACK_SLUG. Empty/non-transliterable input falls
//     back to "untitled" by default.
//
// Usage:
//
//   import { generateSlug } from "./generate-slug.example";
//
//   const slug = await generateSlug("My First Post", {
//     existsFn: async (s) => await Slug.exists(s),
//   });
//
// Reference: SEO for Engineers, Volume 1, Chapter 12.

export const RESERVED_SLUGS: ReadonlySet<string> = new Set([
  "admin", "api", "static", "assets", "login", "logout", "register",
  "search", "feed", "sitemap", "robots", "favicon", "null",
  "undefined", "new", "edit", "delete", "settings", "profile",
  "account", "help", "support", "about", "contact", "privacy",
  "terms", "status", "health", "metrics",
]);

export const FALLBACK_SLUG = "untitled";

export interface SlugOptions {
  /** Maximum slug length. Defaults to 80. */
  maxLength?: number;
  /** Returns true if the slug is already used in the datastore. */
  existsFn?: (slug: string) => Promise<boolean>;
}

/**
 * Generate a URL-safe slug from a title string. Returns FALLBACK_SLUG
 * for empty, whitespace-only, or non-transliterable input.
 */
export async function generateSlug(
  title: string,
  options: SlugOptions = {},
): Promise<string> {
  const { maxLength = 80, existsFn } = options;

  // Step 1, Unicode NFKD normalization makes diacritics easy to
  // strip in step 2.
  // Step 2, strip combining diacritical marks (the U+0300-U+036F
  // range covers most Latin-script diacritics after NFKD).
  // Step 3, lowercase.
  // Step 4, non-alphanumeric runs collapse to a single hyphen.
  // Step 5, collapse consecutive hyphens (defensive, the previous
  // regex already does this, but kept for clarity).
  // Step 6, trim leading and trailing hyphens.
  let slug = title
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "");

  // Step 7, fall back if everything was stripped (whitespace,
  // punctuation, or non-Latin input without transliteration).
  if (!slug) {
    slug = FALLBACK_SLUG;
  }

  // Step 8, word-boundary-aware truncation. If the truncated slug
  // ends mid-word, trim back to the last hyphen so we don't ship
  // a slug like "introduction-to-pyth".
  if (slug.length > maxLength) {
    const truncated = slug.slice(0, maxLength);
    const lastHyphen = truncated.lastIndexOf("-");
    slug = lastHyphen > 0 ? truncated.slice(0, lastHyphen) : truncated;
  }

  // Step 9, reserved-word protection. Treat a reserved match the
  // same way as a datastore collision: append a numeric suffix.
  const baseSlug = slug;
  let counter = 2;
  if (RESERVED_SLUGS.has(slug)) {
    const suffix = `-${counter}`;
    slug = baseSlug.slice(0, maxLength - suffix.length) + suffix;
    counter += 1;
  }

  // Step 10, collision resolution. Shares the counter with step 9
  // so a slug that hits both keeps incrementing.
  if (existsFn) {
    let attempts = 0;
    while (await existsFn(slug)) {
      const suffix = `-${counter}`;
      slug = baseSlug.slice(0, maxLength - suffix.length) + suffix;
      counter += 1;
      attempts += 1;
      if (attempts > 10_000) {
        throw new Error(
          `Could not resolve slug collision for: ${title}`,
        );
      }
    }
  }

  return slug;
}

export function isSlugReserved(slug: string): boolean {
  return RESERVED_SLUGS.has(slug);
}
