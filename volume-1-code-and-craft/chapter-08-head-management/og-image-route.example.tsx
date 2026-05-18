// og-image-route.example.tsx
//
// Reference Next.js App Router route handler that generates Open
// Graph card images on demand from query-string parameters. Drop
// the file at app/api/og/route.tsx in a Next.js 14+ project. The
// route runs on the Edge Runtime and returns a 1200x630 PNG sized
// for X (summary_large_image) and Facebook (large card).
//
// Why this lives here. The chapter argues that every social-card-
// eligible page should have an OG image, that manually designing
// one per page does not scale, and that programmatic generation
// from a typed template is the right answer at scale. This is the
// canonical implementation of that pattern.
//
// Usage from a page's metadata:
//
//   export const metadata = {
//     openGraph: {
//       images: [{
//         url: `/api/og?title=${encodeURIComponent(product.name)}`,
//         width: 1200,
//         height: 630,
//         alt: product.name,
//       }],
//     },
//   };
//
// Notes:
//   - Imports from `next/og`, the modern path (Next.js 14+).
//     `@vercel/og` still works but is the older path.
//   - The Edge runtime keeps the latency low. Cold starts on Node
//     runtime would inflate p99 latency on the social scraper's
//     first fetch.
//   - Encode user-controlled query values with encodeURIComponent
//     at the call site. The route trusts the decoded value here.
//
// Reference: SEO for Engineers, Volume 1, Chapter 8.

import { ImageResponse } from 'next/og';

export const runtime = 'edge';

export async function GET(request: Request): Promise<ImageResponse> {
  const { searchParams } = new URL(request.url);
  const title = searchParams.get('title') ?? 'Default Title';
  const author = searchParams.get('author') ?? '';

  return new ImageResponse(
    (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          width: '100%',
          height: '100%',
          backgroundColor: '#1a1a2e',
          padding: '60px',
        }}
      >
        <div
          style={{
            fontSize: 60,
            fontWeight: 700,
            color: '#ffffff',
            lineHeight: 1.2,
          }}
        >
          {title}
        </div>
        <div
          style={{
            fontSize: 28,
            color: '#94a3b8',
            marginTop: 'auto',
          }}
        >
          {author} · OutdoorGear
        </div>
      </div>
    ),
    { width: 1200, height: 630 },
  );
}
