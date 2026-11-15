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
# Exit codes:
#   0  the origin negotiated HTTP/2
#   1  the origin answered over another protocol (usually HTTP/1.1)
#   2  the request failed (DNS, connection, TLS), so nothing was learned
#
# Reference: SEO for Engineers, Volume 1, Chapter 1.
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <url>" >&2
  exit 1
fi

URL="$1"

# Ask curl for the negotiated version directly. Parsing the first header
# line through `head -1` races curl under pipefail (SIGPIPE on the
# remaining headers), and a failed request would exit silently.
if ! VERSION=$(curl -sS -o /dev/null -I --http2 -w '%{http_version}' "$URL"); then
  echo "Request to $URL failed; protocol unknown" >&2
  exit 2
fi
echo "Protocol: HTTP/$VERSION"

if [[ "$VERSION" == 2* ]]; then
  echo "OK, HTTP/2 supported"
  exit 0
else
  echo "Not serving HTTP/2"
  exit 1
fi