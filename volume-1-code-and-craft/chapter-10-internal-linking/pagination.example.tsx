// pagination.example.tsx
//
// Reference numbered-pagination React component for the pattern
// described in Chapter 10 of SEO for Engineers, Volume 1. Renders
// crawlable <a href> links for first, last, current ± 2, with
// ellipses in between. The first page renders without a `?page=`
// query parameter so the canonical landing form is /category, not
// /category?page=1.
//
// Why numbered (not just prev/next). Numbered links reduce the
// effective click depth of paginated content from O(n) to O(log n).
// Googlebot following only prev/next must walk every page in the
// sequence to reach deep content; numbered links give the crawler
// direct paths to first, last, and a window around the current page.
//
// Usage:
//
//   import { Pagination } from './pagination.example';
//
//   <Pagination
//     currentPage={3}
//     totalPages={42}
//     baseUrl="/products/category"
//   />
//
// Reference: SEO for Engineers, Volume 1, Chapter 10.

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  /** e.g. "/products/category" — appended with `?page=N` for N > 1 */
  baseUrl: string;
}

export function Pagination({
  currentPage,
  totalPages,
  baseUrl,
}: PaginationProps) {
  const getPageUrl = (page: number): string => {
    if (page === 1) return baseUrl;
    return `${baseUrl}?page=${page}`;
  };

  /**
   * Generate the window of page numbers to render: always first and
   * last, plus current ± windowSize, with `ellipsis` between the
   * windows when there is a gap.
   */
  const getPageNumbers = (): (number | 'ellipsis')[] => {
    const pages: (number | 'ellipsis')[] = [];
    const windowSize = 2;

    pages.push(1);

    const rangeStart = Math.max(2, currentPage - windowSize);
    const rangeEnd = Math.min(totalPages - 1, currentPage + windowSize);

    if (rangeStart > 2) pages.push('ellipsis');
    for (let i = rangeStart; i <= rangeEnd; i++) {
      pages.push(i);
    }
    if (rangeEnd < totalPages - 1) pages.push('ellipsis');

    if (totalPages > 1) pages.push(totalPages);

    return pages;
  };

  return (
    <nav aria-label="Pagination">
      {currentPage > 1 && (
        <a href={getPageUrl(currentPage - 1)} rel="prev">
          Previous
        </a>
      )}
      {getPageNumbers().map((page, index) =>
        page === 'ellipsis' ? (
          <span key={`ellipsis-${index}`} aria-hidden="true">
            …
          </span>
        ) : (
          <a
            key={page}
            href={getPageUrl(page)}
            aria-current={page === currentPage ? 'page' : undefined}
          >
            {page}
          </a>
        ),
      )}
      {currentPage < totalPages && (
        <a href={getPageUrl(currentPage + 1)} rel="next">
          Next
        </a>
      )}
    </nav>
  );
}
