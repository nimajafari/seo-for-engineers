/**
 * product_schema.tsx
 *
 * Reference implementation of the ProductSchema React component
 * from Chapter 19 section 19.5.
 *
 * The chapter's central pattern: JSON-LD must be computed from
 * the same data object as the visible body, in the same page
 * function, with no second fetch. Optional fields are
 * conditionally included (not emitted with null or empty
 * strings), which is the schema-correct behavior.
 *
 * Copy this file into your components directory and adapt the
 * Product type to match your CMS schema. The shape below is
 * representative of a typical headless commerce setup.
 */

export interface ProductImage {
  url: string;
  alt?: string;
}

export interface ProductBrand {
  name: string;
}

export interface ProductPrice {
  amount: number;
  currencyCode: string;
}

export interface ProductReviewStats {
  average: number;
  count: number;
}

export interface Product {
  handle: string;
  displayName: string;
  description: string;
  images: ProductImage[];
  sku: string;
  price: ProductPrice;
  availableForSale: boolean;
  brand?: ProductBrand | null;
  reviewStats?: ProductReviewStats | null;
}

interface ProductSchemaProps {
  product: Product;
  origin: string;
}

/**
 * Build a Schema.org Product JSON-LD object from a Product.
 *
 * The function is exported separately from the component so it
 * can be tested in isolation and reused server-side (for example
 * when generating sitemap-level structured data summaries).
 */
export function buildProductJsonLd(
  product: Product,
  origin: string,
): Record<string, unknown> {
  const jsonLd: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.displayName,
    description: product.description,
    image: product.images.map((i) => i.url),
    sku: product.sku,
    offers: {
      '@type': 'Offer',
      url: `${origin}/products/${product.handle}`,
      priceCurrency: product.price.currencyCode,
      price: product.price.amount,
      availability: product.availableForSale
        ? 'https://schema.org/InStock'
        : 'https://schema.org/OutOfStock',
    },
  };

  // Optional fields: include only when data is present.
  // Emitting brand with null or aggregateRating with zero counts
  // is a Schema.org violation that Rich Results Test will flag.
  if (product.brand) {
    jsonLd.brand = {
      '@type': 'Brand',
      name: product.brand.name,
    };
  }

  if (
    product.reviewStats &&
    product.reviewStats.count > 0 &&
    product.reviewStats.average > 0
  ) {
    jsonLd.aggregateRating = {
      '@type': 'AggregateRating',
      ratingValue: product.reviewStats.average,
      reviewCount: product.reviewStats.count,
    };
  }

  return jsonLd;
}

export function ProductSchema({ product, origin }: ProductSchemaProps) {
  const jsonLd = buildProductJsonLd(product, origin);

  return (
    <script
      type="application/ld+json"
      // React escapes JSX content by default, which breaks JSON syntax.
      // dangerouslySetInnerHTML is the standard pattern for JSON-LD in React.
      dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
    />
  );
}