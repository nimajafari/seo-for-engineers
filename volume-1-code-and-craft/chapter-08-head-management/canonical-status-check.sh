#!/usr/bin/env bash
#
# canonical-status-check.sh
#
# Validate every URL in the input file has a canonical tag pointing
# at a URL that returns HTTP 200. Designed to run in CI as a
# regression gate on canonical drift, where a canonical tag continues
# pointing at a URL that has since been redirected, removed, or
# otherwise stopped returning 200.
#
# Usage:
#   ./canonical-status-check.sh urls.txt
#
# urls.txt should contain one URL per line. Blank lines and lines
# starting with `#` are ignored.
#
# Exit codes:
#   0 - every URL's canonical tag returns 200.
#   1 - at least one canonical issue was found.
#   2 - usage error (missing or invalid input file).
#
# Cross-platform notes. The canonical extraction step needs a regex
# engine that supports lookbehind or `\K`. Linux ships GNU grep with
# PCRE support (`-P`). macOS ships BSD grep without `-P`. This script
# detects the local grep at startup and falls back to a perl one-liner
# on systems without GNU grep. Both code paths produce the same
# output, so the rest of the script does not care which engine ran.
#
# The HTML extraction is a first-cut heuristic, not a full parser. It
# matches the common attribute order `<link rel="canonical"
# href="...">`. Pages that emit `<link href="..." rel="canonical">`
# (attributes in the opposite order) or single-quoted attributes will
# not match. For complete coverage, use head-audit.py in this same
# directory.
#
# Reference: SEO for Engineers, Volume 1, Chapter 8.

set -euo pipefail

USER_AGENT="Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; \
+https://github.com/nimajafari/seo-for-engineers)"

# -----------------------------------------------------------------------------
# Argument handling
# -----------------------------------------------------------------------------

URLS_FILE="${1:-}"

if [ -z "$URLS_FILE" ] || [ ! -f "$URLS_FILE" ]; then
    echo "Usage: $0 <urls-file>" >&2
    echo "  urls-file: path to a text file with one URL per line." >&2
    exit 2
fi

# -----------------------------------------------------------------------------
# Detect a regex engine that can extract the canonical href.
#
# Test by running grep -P against a known-matching input. If it
# succeeds, GNU grep is available. If it errors (BSD grep on macOS
# does not implement -P), fall back to perl, which ships by default
# on macOS and on most Linux distributions.
# -----------------------------------------------------------------------------

if echo "test" | grep -P "test" >/dev/null 2>&1; then
    HAS_GREP_PCRE=1
else
    HAS_GREP_PCRE=0
fi

# Emit every canonical href found, one per line, so the caller can both
# take the first and detect duplicates (multiple canonicals are a
# high-severity signal: Google typically ignores all of them).
extract_canonicals() {
    if [ "$HAS_GREP_PCRE" -eq 1 ]; then
        # GNU grep with PCRE. Linux, GitHub Actions Ubuntu runners,
        # most CI environments.
        grep -oiP '<link\s+rel="canonical"\s+href="\K[^"]+'
    else
        # BSD grep on macOS does not implement -P. Fall back to perl,
        # which is POSIX-portable.
        perl -ne 'while (/<link\s+rel="canonical"\s+href="([^"]+)"/ig) { print "$1\n"; }'
    fi
}

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

failures=0
checked=0

while IFS= read -r url || [ -n "$url" ]; do
    # Skip blanks and comments.
    case "$url" in
        ""|\#*) continue ;;
    esac

    checked=$((checked + 1))

    html=$(curl -sSL -A "$USER_AGENT" "$url" || true)
    if [ -z "$html" ]; then
        echo "FAIL: $url could not be fetched"
        failures=$((failures + 1))
        continue
    fi

    canonicals=$(printf '%s' "$html" | extract_canonicals || true)
    if [ -z "$canonicals" ]; then
        echo "FAIL: $url has no <link rel=\"canonical\"> tag"
        failures=$((failures + 1))
        continue
    fi

    canonical_count=$(printf '%s\n' "$canonicals" | grep -c . || true)
    if [ "$canonical_count" -gt 1 ]; then
        echo "FAIL: $url has $canonical_count canonical tags (Google ignores all of them)"
        failures=$((failures + 1))
        continue
    fi

    canonical=$(printf '%s\n' "$canonicals" | head -n1)

    status=$(curl -sSL -A "$USER_AGENT" -o /dev/null \
        -w "%{http_code}" "$canonical" || echo "000")
    if [ "$status" != "200" ]; then
        echo "FAIL: $url -> canonical=$canonical (HTTP $status)"
        failures=$((failures + 1))
    fi
done < "$URLS_FILE"

# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

echo ""
if [ "$failures" -gt 0 ]; then
    echo "$failures canonical issue(s) found across $checked URL(s)." >&2
    exit 1
fi

echo "All $checked canonical URLs return 200."
