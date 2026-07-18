#!/bin/bash
# CI check, validate that all internal links in the rendered HTML
# point to URLs that return 200.
#
# Portability. GNU grep (Linux, most CI runners) supports -P (PCRE).
# BSD grep on macOS does not. Detect capability at startup and fall
# back to perl, which ships by default on macOS and most Linux systems.
# Same approach as canonical-status-check.sh (chapter-08) and
# internal-link-validator.sh (this chapter).

set -euo pipefail

BASE_URL="https://example.com"
BASE_HOST="example.com"
export BASE_HOST

# -----------------------------------------------------------------------------
# Cross-platform extractors
# -----------------------------------------------------------------------------

if echo "test" | grep -P "test" >/dev/null 2>&1; then
  extract_locs() {
    grep -oP '<loc>\K[^<]+'
  }
  extract_hrefs() {
    # Match both relative paths (/foo) and absolute URLs on the same host.
    grep -oP "href=\"\K(?:https?://(?:www\.)?${BASE_HOST})?/[^\"]*"
  }
else
  extract_locs() {
    perl -ne 'print "$1\n" while /<loc>([^<]+)/g'
  }
  extract_hrefs() {
    # Escape dots in the host for the regex; BASE_HOST is set above.
    perl -ne '
      BEGIN { $host = quotemeta($ENV{BASE_HOST}); }
      while (/href="((?:https?:\/\/(?:www\.)?$host)?\/[^"]*)"/g) {
        print "$1\n";
      }
    '
  }
fi

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

echo "Fetching sitemap: ${BASE_URL}/sitemap.xml"
SITEMAP_URLS=$(curl -sS "${BASE_URL}/sitemap.xml" | extract_locs || true)

if [ -z "$SITEMAP_URLS" ]; then
  echo "ERROR: no URLs found in sitemap" >&2
  exit 1
fi

ERRORS=0
CHECKED=0

for url in $SITEMAP_URLS; do
  echo ""
  echo "Page: $url"

  LINKS=$(curl -sS "$url" | extract_hrefs | sort -u || true)

  if [ -z "$LINKS" ]; then
    echo "  (no internal links found)"
    continue
  fi

  for link in $LINKS; do
    if [[ "$link" == /* ]]; then
      FULL_URL="${BASE_URL}${link}"
    else
      FULL_URL="$link"
    fi

    STATUS=$(curl -sS -o /dev/null -w "%{http_code}" "$FULL_URL" || echo "000")
    CHECKED=$((CHECKED + 1))

    if [ "$STATUS" = "200" ]; then
      echo "  OK   $STATUS  $FULL_URL"
    else
      echo "  FAIL $STATUS  $FULL_URL  (from $url)"
      ERRORS=$((ERRORS + 1))
    fi
  done
done

echo ""
if [ "$ERRORS" -gt 0 ]; then
  echo "FAILED: $ERRORS broken internal link(s) out of $CHECKED checked"
  exit 1
fi

echo "PASSED: all $CHECKED internal links return 200"
