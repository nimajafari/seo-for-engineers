// schema-builder.example.ts
//
// Reference TypeScript builder for the structured-data pattern
// described in Chapter 9 of SEO for Engineers, Volume 1.
//
// The builder pattern centralizes the mapping between application
// data models and Schema.org types. Each builder owns its required-
// field validation, its enumeration mapping, and its sanitization,
// so the rest of the application never assembles raw JSON-LD by
// hand. Builders return `null` (not an incomplete object) when
// required fields are missing, on the principle that it is always
// better to emit no structured data than invalid structured data.
//
// Usage:
//
//   import { ProductSchemaBuilder, BreadcrumbSchemaBuilder }
//     from './schema-builder.example';
//
//   const productSchema = new ProductSchemaBuilder().build(product);
//   const breadcrumbSchema = new BreadcrumbSchemaBuilder().build(crumbs);
//
//   // Render each non-null schema as its own <script
//   // type="application/ld+json"> block.
//
// Differences from the chapter version:
//   - description is sanitized only when present (the chapter
//     version crashes if description is undefined).
//   - mapAvailability includes Discontinued, matching the chapter's
//     Django _availability_url helper and the structured-data-
//     extractor.py validator in this directory.
//   - the escape helper is shared, so BreadcrumbSchemaBuilder sanitizes
//     its labels too, not just ProductSchemaBuilder.
//
// Reference: SEO for Engineers, Volume 1, Chapter 9.

/**
 * Three-character escape that stops a JSON-LD string value from breaking
 * out of the surrounding <script> tag. Shared by every builder so that
 * all user-controllable strings (product names, breadcrumb labels, ...)
 * are escaped consistently. This is the Failure Mode 8 defense from
 * Chapter 9; any builder that emits an unescaped string reopens the XSS
 * hole the extractor's unsanitized_user_content check exists to catch.
 */
export function escapeJsonLd(input: string): string {
  return input
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026');
}

export interface ProductImage {
  url?: string;
}

export interface ProductPageData {
  name: string;
  sku: string;
  description?: string;
  brand?: string;
  gtin?: string;
  images: ProductImage[];
  canonicalUrl: string;
  currency: string;
  price: number;
  availability: string;
  reviewCount: number;
  averageRating?: number;
}

export interface BreadcrumbData {
  label: string;
  url: string;
}

export interface SchemaBuilder<T> {
  build(data: T): Record<string, unknown> | null;
}

export class ProductSchemaBuilder implements SchemaBuilder<ProductPageData> {
  build(data: ProductPageData): Record<string, unknown> | null {
    // Refuse to generate incomplete structured data. The chapter's
    // strict rule: every required Google field must be present, or
    // we emit nothing.
    if (!data.name || data.price == null) {
      // eslint-disable-next-line no-console
      console.warn(
        `Structured data skipped for product ${data.sku}: ` +
          'missing required fields (name and price)',
      );
      return null;
    }

    const schema: Record<string, unknown> = {
      '@context': 'https://schema.org',
      '@type': 'Product',
      name: this.sanitize(data.name),
      sku: data.sku,
      image: data.images.filter((img) => img.url).map((img) => img.url as string),
    };

    // Description is optional. Sanitize only when present so an
    // undefined description does not crash the builder.
    if (data.description) {
      schema.description = this.sanitize(data.description);
    }
    if (data.brand) {
      schema.brand = { '@type': 'Brand', name: this.sanitize(data.brand) };
    }
    if (data.gtin) {
      schema.gtin13 = data.gtin;
    }

    schema.offers = {
      '@type': 'Offer',
      url: data.canonicalUrl,
      priceCurrency: data.currency,
      price: data.price,
      availability: this.mapAvailability(data.availability),
      itemCondition: 'https://schema.org/NewCondition',
    };

    if (data.reviewCount > 0 && data.averageRating) {
      schema.aggregateRating = {
        '@type': 'AggregateRating',
        ratingValue: Math.round(data.averageRating * 10) / 10,
        reviewCount: data.reviewCount,
      };
    }

    return schema;
  }

  private sanitize(input: string): string {
    return escapeJsonLd(input);
  }

  private mapAvailability(status: string): string {
    const map: Record<string, string> = {
      in_stock: 'https://schema.org/InStock',
      out_of_stock: 'https://schema.org/OutOfStock',
      preorder: 'https://schema.org/PreOrder',
      backorder: 'https://schema.org/BackOrder',
      discontinued: 'https://schema.org/Discontinued',
    };
    return map[status] || 'https://schema.org/OutOfStock';
  }
}

export class BreadcrumbSchemaBuilder
  implements SchemaBuilder<BreadcrumbData[]>
{
  build(data: BreadcrumbData[]): Record<string, unknown> | null {
    if (!data.length) {
      return null;
    }
    return {
      '@context': 'https://schema.org',
      '@type': 'BreadcrumbList',
      // Breadcrumb labels are page-derived (category names, titles) and
      // must be escaped just like product fields, or they reopen the
      // Failure Mode 8 injection hole.
      itemListElement: data.map((item, index) => ({
        '@type': 'ListItem',
        position: index + 1,
        name: escapeJsonLd(item.label),
        item: item.url,
      })),
    };
  }
}
