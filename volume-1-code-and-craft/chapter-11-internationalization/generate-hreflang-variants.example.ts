// generate-hreflang-variants.example.ts
//
// Framework-agnostic TypeScript helper that derives the hreflang
// variant URLs for the current page from its path and locale,
// described in Chapter 11 of SEO for Engineers, Volume 1.
//
// Use this when locale URLs follow a consistent pattern, where the
// slug is the same across locales and only the leading locale
// segment changes:
//
//   /en/product/widget    /de/product/widget    /fr/product/widget
//
// If your site translates slugs per locale (/de/produkt/widget
// rather than /de/product/widget), this pattern-based helper does
// not work. The variant mapping must come from the CMS or database
// in that case. The chapter discusses this trade-off explicitly.
//
// Usage with the Next.js App Router Metadata API:
//
//   import type { Metadata } from "next";
//   import { generateHreflangVariants } from "./generate-hreflang-variants.example";
//
//   export async function generateMetadata({ params }): Promise<Metadata> {
//     const { locale, slug } = await params;
//     const variants = generateHreflangVariants(
//       `/${locale}/product/${slug}`, locale,
//     );
//     return {
//       alternates: {
//         languages: {
//           ...Object.fromEntries(variants.map((v) => [v.locale, v.url])),
//           "x-default": `https://example.com/product/${slug}`,
//         },
//       },
//     };
//   }
//
// Reference: SEO for Engineers, Volume 1, Chapter 11.

export const SUPPORTED_LOCALES = [
  "en",
  "de",
  "fr",
  "es",
  "ja",
  "en-gb",
  "en-us",
] as const;

export const DEFAULT_LOCALE = "en";
export const BASE_URL = "https://example.com";

export interface LocaleVariant {
  locale: string;
  url: string;
}

/**
 * Derive the full set of hreflang variant URLs for the current page.
 *
 * @param currentPath    The full request path including the leading
 *                       locale segment, e.g. "/de/product/widget".
 * @param currentLocale  The locale segment of currentPath, e.g. "de".
 *                       Must match the locale prefix in currentPath
 *                       exactly; otherwise the prefix-strip step is
 *                       a no-op and every variant URL repeats the
 *                       original locale segment.
 * @param availableLocales  Locales to emit variants for. Defaults to
 *                          SUPPORTED_LOCALES. Pass a subset when a
 *                          page is only published in some locales.
 */
export function generateHreflangVariants(
  currentPath: string,
  currentLocale: string,
  availableLocales: readonly string[] = SUPPORTED_LOCALES,
): LocaleVariant[] {
  // Escape currentLocale so a locale containing regex metacharacters
  // (none of the SUPPORTED_LOCALES do today, but it is defensive
  // against future additions or caller error) cannot break the
  // pattern.
  const escaped = currentLocale.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pathWithoutLocale = currentPath.replace(
    new RegExp(`^/${escaped}(/|$)`),
    "/",
  );

  return availableLocales.map((locale) => ({
    locale,
    url: `${BASE_URL}/${locale}${pathWithoutLocale}`.replace(/\/$/, ""),
  }));
}
