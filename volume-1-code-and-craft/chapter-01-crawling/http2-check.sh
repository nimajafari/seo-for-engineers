#!/usr/bin/env bash
#
# http2-check.sh
#
# Verify whether an origin is serving HTTP/2 to clients that request it.
# Googlebot supports HTTP/2 and will use it when available. Origins still
# serving HTTP/1.1 to Googlebot are leaving crawl efficiency on the table.
#
# Usage:
#   ./http2-check.sh https://example.com
#
# Exits 0 if HTTP/2 is supported, 1 otherwise.
#
# Reference: SEO for Engineers, Volume 1, Chapter 1.
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <url>" >&2
  exit 1
fi

URL="$1"

PROTO=$(curl -sI --http2 "$URL" | head -1 | awk '{print $1}')
echo "Protocol: $PROTO"

if [[ "$PROTO" == HTTP/2* ]]; then
  echo "OK, HTTP/2 supported"
  exit 0
else
  echo "Not serving HTTP/2"
  exit 1
fi