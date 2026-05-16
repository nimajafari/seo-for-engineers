#!/usr/bin/env bash
#
# compare-raw-vs-rendered.sh
#
# Fetch a URL twice. Once as Googlebot (wave one), once as a normal
# browser. Print both responses with a banner between them so you can
# eyeball the rendering gap, or pipe each side to a file and run diff.
#
# Usage:
#   ./compare-raw-vs-rendered.sh https://example.com/page
#
# Reference: SEO for Engineers, Volume 1, Chapter 2.
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <url>" >&2
  exit 1
fi

URL="$1"

GOOGLEBOT_UA="Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BROWSER_UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

echo "=================================================================="
echo "Wave-one view (Googlebot user-agent), $URL"
echo "=================================================================="
curl -sSL -A "$GOOGLEBOT_UA" "$URL"

echo ""
echo "=================================================================="
echo "Browser view (Chrome user-agent), $URL"
echo "=================================================================="
curl -sSL -A "$BROWSER_UA" "$URL"