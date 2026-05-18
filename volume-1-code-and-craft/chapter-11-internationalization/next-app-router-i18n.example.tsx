// next-app-router-i18n.example.tsx
//
// Reference Next.js 15+ App Router i18n composition for the
// patterns described in Chapter 11 of SEO for Engineers, Volume 1.
// In a real project these would live in three separate files:
//
//   app/[locale]/layout.tsx                       LocaleLayout
//   app/[locale]/product/[slug]/page.tsx          ProductPage
//   app/[locale]/product/[slug]/generateMetadata  generateMetadata
//
// They are colocated here so you can read the entire composition
// in one place. The key contracts:
//
//   - Locale flows from the URL into <html lang>, into the
//     translation scope, and into the hreflang variants.
//   - All locale-sensitive work happens server-side, before render.
//     Translation strings are resolved by getTranslations on the
//     server, so Googlebot's first-wave fetch sees fully localized
//     HTML with no JavaScript dependency.
//   - hreflang annotations are emitted via Metadata.alternates.
//     languages. Next.js renders one <link rel="alternate"
//     hreflang="..."> per entry, plus a self-canonical, plus
//     x-default.
//   - params is Promise<...> in Next.js 15+. Every locale-aware
//     function awaits it before reading locale or slug.
//
// Reference: SEO for Engineers, Volume 1, Chapter 11.

import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import {
  generateHreflangVariants,
  BASE_URL,
} from "./generate-hreflang-variants.example";

interface Product {
  localizedName: string;
  price: number;
  currency: string;
  inStock: boolean;
}

// Stub. Replace with your real data layer.
declare function fetchProduct(slug: string, locale: string): Promise<Product>;

// ---------------------------------------------------------------------------
// app/[locale]/layout.tsx
// ---------------------------------------------------------------------------
// Sets <html lang> from the URL's locale segment. The locale flows
// down into every child route via the request scope (set by the
// page below via setRequestLocale).
// ---------------------------------------------------------------------------

export async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return (
    <html lang={locale}>
      <body>{children}</body>
    </html>
  );
}

// ---------------------------------------------------------------------------
// app/[locale]/product/[slug]/page.tsx
// ---------------------------------------------------------------------------
// Async Server Component. Resolves locale and slug from the route,
// pins the request scope, fetches the localized product and the
// translation bundle, and renders fully translated HTML before
// returning. Googlebot's first-wave fetch sees the final markup
// with no JavaScript execution required.
// ---------------------------------------------------------------------------

interface ProductPageProps {
  params: Promise<{ locale: string; slug: string }>;
}

export default async function ProductPage({ params }: ProductPageProps) {
  const { locale, slug } = await params;

  // Pin the request scope so getTranslations resolves the correct
  // message bundle for this locale.
  setRequestLocale(locale);

  const product = await fetchProduct(slug, locale);
  const t = await getTranslations("product");

  return (
    <main>
      <h1>{product.localizedName}</h1>
      <p>{t("description", { name: product.localizedName })}</p>
      <p>
        {t("price", { amount: product.price, currency: product.currency })}
      </p>
      <p>
        {t("availability")}:{" "}
        {t(product.inStock ? "inStock" : "outOfStock")}
      </p>
    </main>
  );
}

// ---------------------------------------------------------------------------
// generateMetadata: hreflang via alternates.languages
// ---------------------------------------------------------------------------
// Emits one <link rel="alternate" hreflang="X" href="..."> per
// declared locale, plus an x-default, plus a self-referencing
// canonical. Next.js renders all of these into <head> for us; the
// page component does not need to inject anything by hand.
// ---------------------------------------------------------------------------

export async function generateMetadata({
  params,
}: ProductPageProps): Promise<Metadata> {
  const { locale, slug } = await params;

  const variants = generateHreflangVariants(
    `/${locale}/product/${slug}`,
    locale,
  );

  return {
    alternates: {
      canonical: `${BASE_URL}/${locale}/product/${slug}`,
      languages: {
        ...Object.fromEntries(variants.map((v) => [v.locale, v.url])),
        "x-default": `${BASE_URL}/product/${slug}`,
      },
    },
  };
}
