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
#   ./compare-raw-vs-rendered.sh https://example.com/page out/
#
# With an output directory, the two bodies are saved as googlebot.html
# and browser.html instead of printed, ready for `diff`. Either way, a
# summary line per user-agent reports the HTTP status and final URL after
# redirects: a 403 or a different redirect target for Googlebot is the
# user-agent-adaptive serving this script exists to surface.
#
# Exit codes:
#   0  both fetches completed (whatever their HTTP status)
#   2  a fetch failed outright (DNS, connection, TLS, timeout)
#
# Reference: SEO for Engineers, Volume 1, Chapter 2.
#

set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  echo "Usage: $0 <url> [out-dir]" >&2
  exit 1
fi

URL="$1"
OUT_DIR="${2:-}"

GOOGLEBOT_UA="Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
BROWSER_UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"

if [ -n "$OUT_DIR" ]; then
  mkdir -p "$OUT_DIR"
  WORK_DIR="$OUT_DIR"
else
  WORK_DIR=$(mktemp -d)
  trap 'rm -rf "$WORK_DIR"' EXIT
fi

# fetch <label> <user-agent> <file>: save the body to <file> and print
# "<status> <final-url>". Exits 2 on a transport failure; an HTTP error
# status is a result worth comparing, not a failure.
fetch() {
  local meta
  if ! meta=$(curl -sSL --max-time 30 -A "$2" -o "$3" \
      -w '%{http_code} %{url_effective}' "$URL"); then
    echo "Fetch as $1 failed for $URL" >&2
    exit 2
  fi
  printf '%s\n' "$meta"
}

GB_META=$(fetch "Googlebot" "$GOOGLEBOT_UA" "$WORK_DIR/googlebot.html")
BR_META=$(fetch "browser" "$BROWSER_UA" "$WORK_DIR/browser.html")

if [ -z "$OUT_DIR" ]; then
  echo "=================================================================="
  echo "Server response to Googlebot user-agent (no JS executed), $URL"
  echo "=================================================================="
  cat "$WORK_DIR/googlebot.html"

  echo ""
  echo "=================================================================="
  echo "Server response to desktop-browser user-agent (no JS executed), $URL"
  echo "=================================================================="
  cat "$WORK_DIR/browser.html"
  echo ""
fi

GB_BYTES=$(wc -c < "$WORK_DIR/googlebot.html" | tr -d ' ')
BR_BYTES=$(wc -c < "$WORK_DIR/browser.html" | tr -d ' ')

echo "=================================================================="
echo "Summary (HTTP status, final URL, body size)"
echo "=================================================================="
echo "Googlebot: HTTP ${GB_META%% *}  ${GB_META#* }  ${GB_BYTES} bytes"
echo "Browser:   HTTP ${BR_META%% *}  ${BR_META#* }  ${BR_BYTES} bytes"
if [ "$GB_META" != "$BR_META" ]; then
  echo "Status or final URL differs by user-agent: check for UA-adaptive serving."
elif cmp -s "$WORK_DIR/googlebot.html" "$WORK_DIR/browser.html"; then
  echo "Bodies are identical."
else
  echo "Bodies differ (nonces and timestamps also cause this; diff to inspect)."
fi
if [ -n "$OUT_DIR" ]; then
  echo "Saved: $OUT_DIR/googlebot.html, $OUT_DIR/browser.html"
fi
