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
# Each time is measured from the start of the request (curl's cumulative
# timers), so TLS includes DNS and TCP. The HTTP status is printed too: a
# fast 404 or 5xx is not a fast page. Exits 2 if the request fails, rather
# than printing zero timings.
#
# Reference: SEO for Engineers, Volume 1, Chapter 1.
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <url>" >&2
  exit 1
fi

URL="$1"

if ! TIMINGS=$(curl -o /dev/null -sS -w \
  "HTTP:  %{http_code}\nDNS:   %{time_namelookup}s\nTCP:   %{time_connect}s\nTLS:   %{time_appconnect}s\nTTFB:  %{time_starttransfer}s\nTotal: %{time_total}s\n" \
  "$URL"); then
  echo "Request to $URL failed; no timings recorded" >&2
  exit 2
fi
printf '%s\n' "$TIMINGS"