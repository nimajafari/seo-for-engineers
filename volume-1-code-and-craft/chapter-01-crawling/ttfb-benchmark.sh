#!/usr/bin/env bash
#
# ttfb-benchmark.sh
#
# Measure TTFB and the underlying connection breakdown for a single URL,
# as Googlebot might experience it. Useful for verifying origin response
# times before a deployment, or for spot-checking a slow crawl.
#
# Usage:
#   ./ttfb-benchmark.sh https://example.com/page
#
# Reference: SEO for Engineers, Volume 1, Chapter 1.
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <url>" >&2
  exit 1
fi

URL="$1"

curl -o /dev/null -s -w \
  "DNS:   %{time_namelookup}s\nTCP:   %{time_connect}s\nTLS:   %{time_appconnect}s\nTTFB:  %{time_starttransfer}s\nTotal: %{time_total}s\n" \
  "$URL"