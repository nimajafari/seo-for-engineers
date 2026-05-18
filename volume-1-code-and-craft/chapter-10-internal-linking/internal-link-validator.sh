#!/usr/bin/env bash
#
# internal-link-validator.sh
#
# Validate that every internal link rendered by a list of URLs
# returns HTTP 200. Designed to run in CI as a regression gate
# against broken internal links, the link-equity-leakage failure
# mode described in Chapter 10.
#
# Pairs with chapter-08-head-management/canonical-status-check.sh.
# Where that script verifies one specific link per page (the
# canonical tag), this script verifies every internal anchor.
#
# Usage:
#
#   ./internal-link-validator.sh \
#       --base-url https://example.com \
#       --urls-file urls.txt
#
# urls.txt should contain one URL per line. Lines starting with
# `#` and blank lines are ignored.
#
# Exit codes:
#   0 - every internal link on every URL returns 200.
#   1 - at least one broken internal link was found.
#   2 - usage error (missing input file or required flag).
#
# Cross-platform notes. The regex extraction step uses GNU grep's
# PCRE support (-P) on Linux and falls back to a perl one-liner
# on macOS (BSD grep). The detection runs once at startup, so the
# per-URL loop never re-checks.
#
# Same-host filter. Anchor tags can reference relative paths
# (/foo/bar) or absolute URLs (https://example.com/foo/bar). This
# script extracts both, then keeps only those whose host matches
# the configured base URL.
#
# Reference: SEO for Engineers, Volume 1, Chapter 10.

set -euo pipefail

USER_AGENT="Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; \
+https://github.com/nimajafari/seo-for-engineers)"

# -----------------------------------------------------------------------------
# Argument parsing
# -----------------------------------------------------------------------------

BASE_URL=""
URLS_FILE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --base-url)   BASE_URL="$2"; shift 2 ;;
        --urls-file)  URLS_FILE="$2"; shift 2 ;;
        *)
            echo "Usage: $0 --base-url <url> --urls-file <path>" >&2
            exit 2
            ;;
    esac
done

if [ -z "$BASE_URL" ] || [ -z "$URLS_FILE" ] || [ ! -f "$URLS_FILE" ]; then
    echo "Usage: $0 --base-url <url> --urls-file <path>" >&2
    echo "  --base-url   Origin of the site under test (e.g. https://example.com)" >&2
    echo "  --urls-file  Path to a text file with one URL per line" >&2
    exit 2
fi

# Strip a trailing slash from the base URL so we can concatenate
# relative paths cleanly.
BASE_URL="${BASE_URL%/}"

# Extract the host from the base URL for the same-host filter.
BASE_HOST=$(printf '%s' "$BASE_URL" | sed -E 's#^https?://([^/]+).*#\1#')

# -----------------------------------------------------------------------------
# Cross-platform href extractor
# -----------------------------------------------------------------------------

if echo "test" | grep -P "test" >/dev/null 2>&1; then
    extract_hrefs() {
        # GNU grep with PCRE.
        grep -oP 'href="\K[^"]+'
    }
else
    extract_hrefs() {
        # BSD grep on macOS does not implement -P. Perl is
        # POSIX-portable and ships on macOS by default.
        perl -ne 'print "$1\n" while /href="([^"]+)"/g'
    }
fi

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

errors=0
checked_pages=0
checked_links=0

while IFS= read -r page_url || [ -n "$page_url" ]; do
    case "$page_url" in ""|\#*) continue ;; esac
    checked_pages=$((checked_pages + 1))

    html=$(curl -sSL -A "$USER_AGENT" "$page_url" || true)
    if [ -z "$html" ]; then
        echo "FAIL: $page_url could not be fetched"
        errors=$((errors + 1))
        continue
    fi

    # Extract every href value, then keep only same-host links
    # (relative paths and absolute URLs on the configured base host).
    links=$(printf '%s' "$html" \
        | extract_hrefs \
        | grep -E "^(/[^/]|https?://(www\.)?${BASE_HOST}/)" \
        | sort -u || true)

    for link in $links; do
        # Normalize to an absolute URL before requesting.
        if [ "${link:0:1}" = "/" ]; then
            full_url="${BASE_URL}${link}"
        else
            full_url="$link"
        fi

        checked_links=$((checked_links + 1))
        status=$(curl -sSL -A "$USER_AGENT" -o /dev/null \
            -w "%{http_code}" "$full_url" || echo "000")
        if [ "$status" != "200" ]; then
            echo "FAIL: $page_url -> $full_url (HTTP $status)"
            errors=$((errors + 1))
        fi
    done
done < "$URLS_FILE"

# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

echo ""
if [ "$errors" -gt 0 ]; then
    echo "$errors broken internal link(s) found across $checked_pages page(s)." >&2
    exit 1
fi

echo "All $checked_links internal links across $checked_pages page(s) return 200."
