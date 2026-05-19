#!/usr/bin/env bash
# check-robots-google-parser.sh
#
# Validate that critical URLs remain crawlable by Googlebot, using
# Google's open-source robots.txt parser (github.com/google/robotstxt).
#
# Prerequisites:
#   - The `robots` binary built from github.com/google/robotstxt is
#     available on PATH. See the README for build instructions.
#
# Usage:
#   ./check-robots-google-parser.sh [path/to/robots.txt]
#
# If no path is given, defaults to public/robots.txt.

set -euo pipefail

ROBOTS_FILE="${1:-public/robots.txt}"

if [[ ! -f "$ROBOTS_FILE" ]]; then
  echo "FAIL: robots.txt not found at $ROBOTS_FILE"
  exit 1
fi

if ! command -v robots >/dev/null 2>&1; then
  echo "FAIL: the 'robots' binary is not on PATH."
  echo "Build it from github.com/google/robotstxt and add it to PATH."
  exit 1
fi

CRAWLABLE_URLS=(
  "https://www.example.com/"
  "https://www.example.com/products/"
  "https://www.example.com/products/category/shoes"
  "https://www.example.com/blog/"
  "https://www.example.com/sitemap.xml"
  "https://www.example.com/static/app.css"
  "https://www.example.com/static/app.js"
)

BLOCKED_URLS=(
  "https://www.example.com/admin/"
  "https://www.example.com/cart"
  "https://www.example.com/account/settings"
)

fail=0

for url in "${CRAWLABLE_URLS[@]}"; do
  result=$(robots "$ROBOTS_FILE" "Googlebot" "$url")
  if [[ "$result" != "ALLOWED" ]]; then
    echo "FAIL: $url should be ALLOWED but got $result"
    fail=1
  fi
done

for url in "${BLOCKED_URLS[@]}"; do
  result=$(robots "$ROBOTS_FILE" "Googlebot" "$url")
  if [[ "$result" != "DISALLOWED" ]]; then
    echo "FAIL: $url should be DISALLOWED but got $result"
    fail=1
  fi
done

if [[ $fail -eq 0 ]]; then
  echo "OK: all assertions passed"
fi

exit $fail