#!/usr/bin/env bash
#
# compare-raw-vs-rendered.sh
#
# Fetch a URL twice with curl: once with the Googlebot user-agent and
# once with a desktop-browser user-agent. Print both responses with a
# banner between them so you can diff what the SERVER returns for each.
#
# Important: curl does not execute JavaScript. This compares the two
# server responses, so it surfaces user-agent-adaptive serving and
# cloaking (the server handing Googlebot different HTML than a browser),
# NOT the client-side rendering gap. For a client-rendered SPA both
# fetches usually return the same shell, so this shows no difference even
# when the JavaScript rendering gap is large. To measure that gap, where
# content is injected after load, use rendering-debt-audit.py in this
# directory, which runs a real headless browser.
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
echo "Server response to Googlebot user-agent (no JS executed), $URL"
echo "=================================================================="
curl -sSL -A "$GOOGLEBOT_UA" "$URL"

echo ""
echo "=================================================================="
echo "Server response to desktop-browser user-agent (no JS executed), $URL"
echo "=================================================================="
curl -sSL -A "$BROWSER_UA" "$URL"