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
# For each URL the script fetches the page (following redirects),
# fails it if the page itself returns an HTTP error, and extracts the
# canonical href. It then requests the canonical URL without
# following redirects: the canonical must answer 200 itself, since a
# canonical that redirects to a 200 is exactly the drift this gate
# exists to catch.
#
# Exit codes:
#   0 - every URL's canonical returns 200.
#   1 - at least one canonical issue was found.
#   2 - usage error (missing, unreadable, or empty input file, or
#       curl or perl not installed).
#
# Extraction. A perl one-liner (perl ships with macOS and the usual
# Linux CI images) reads the page up to </head>, drops HTML comments,
# and prints the href of every <link> whose rel includes "canonical",
# in any attribute order and with double, single, or no quotes. It is
# still a regular expression, not an HTML parser; head-audit.py in
# this directory parses the page properly.
#
# Reference: SEO for Engineers, Volume 1, Chapter 8.

set -euo pipefail

USER_AGENT="Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; \
+https://github.com/nimajafari/seo-for-engineers)"
TIMEOUT_SECONDS=30

# -----------------------------------------------------------------------------
# Argument handling
# -----------------------------------------------------------------------------

URLS_FILE="${1:-}"

if [ -z "$URLS_FILE" ] || [ ! -f "$URLS_FILE" ] || [ ! -r "$URLS_FILE" ]; then
    echo "Usage: $0 <urls-file>" >&2
    echo "  urls-file: path to a text file with one URL per line." >&2
    exit 2
fi

for tool in curl perl; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "$0: $tool is required but not installed." >&2
        exit 2
    fi
done

# Emit every canonical href found in <head>, one per line, so the
# caller can both take the first and detect duplicates (multiple
# canonicals are a high-severity signal: Google typically ignores all
# of them). A canonical tag with no href prints "<empty>".
extract_canonicals() {
    perl -0777 -ne '
        s/<!--.*?-->//gs;
        $_ = $1 if m{^(.*?)</head\s*>}is;
        while (m{<link\b([^>]*)>}gis) {
            my $attrs = $1;
            my %attr;
            while ($attrs =~ m{([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|\x27([^\x27]*)\x27|([^\s>]+)))?}g) {
                $attr{lc $1} = $2 // $3 // $4 // "";
            }
            next unless grep { lc($_) eq "canonical" } split " ", ($attr{rel} // "");
            my $href = $attr{href} // "";
            $href =~ s/^\s+|\s+$//g;
            $href =~ s/&amp;/&/gi;
            print length($href) ? "$href\n" : "<empty>\n";
        }'
}

# -----------------------------------------------------------------------------
# Main loop
# -----------------------------------------------------------------------------

failures=0
checked=0
page_file=$(mktemp)
trap 'rm -f "$page_file"' EXIT

while IFS= read -r line || [ -n "$line" ]; do
    # Trim surrounding whitespace, including the \r of CRLF files.
    url="${line#"${line%%[![:space:]]*}"}"
    url="${url%"${url##*[![:space:]]}"}"

    # Skip blanks and comments.
    case "$url" in
        ""|\#*) continue ;;
    esac

    checked=$((checked + 1))

    # curl prints 000 for http_code when the request itself failed.
    page_status=$(curl -sL -A "$USER_AGENT" --max-time "$TIMEOUT_SECONDS" \
        -o "$page_file" -w "%{http_code}" "$url" || true)
    if [ -z "$page_status" ] || [ "$page_status" = "000" ]; then
        echo "FAIL: $url could not be fetched"
        failures=$((failures + 1))
        continue
    fi
    if [ "$page_status" -ge 400 ]; then
        echo "FAIL: $url returned HTTP $page_status"
        failures=$((failures + 1))
        continue
    fi

    canonicals=$(extract_canonicals < "$page_file" || true)
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
    if [ "$canonical" = "<empty>" ]; then
        echo "FAIL: $url has a canonical tag with no href"
        failures=$((failures + 1))
        continue
    fi
    if ! printf '%s' "$canonical" | grep -qiE '^https?://'; then
        echo "FAIL: $url -> canonical=$canonical is not an absolute URL"
        failures=$((failures + 1))
        continue
    fi

    # No -L: the canonical has to answer 200 itself.
    result=$(curl -s -A "$USER_AGENT" --max-time "$TIMEOUT_SECONDS" -o /dev/null \
        -w "%{http_code} %{redirect_url}" "$canonical" || true)
    status="${result%% *}"
    location="${result#* }"
    if [ -z "$status" ] || [ "$status" = "000" ]; then
        echo "FAIL: $url -> canonical=$canonical is unreachable"
        failures=$((failures + 1))
    elif [ "${status:0:1}" = "3" ]; then
        echo "FAIL: $url -> canonical=$canonical redirects (HTTP $status to $location)"
        failures=$((failures + 1))
    elif [ "$status" != "200" ]; then
        echo "FAIL: $url -> canonical=$canonical (HTTP $status)"
        failures=$((failures + 1))
    fi
done < "$URLS_FILE"

# -----------------------------------------------------------------------------
# Report
# -----------------------------------------------------------------------------

if [ "$checked" -eq 0 ]; then
    echo "$0: $URLS_FILE lists no URLs." >&2
    exit 2
fi

echo ""
if [ "$failures" -gt 0 ]; then
    echo "$failures canonical issue(s) found across $checked URL(s)." >&2
    exit 1
fi

echo "All $checked canonical URLs return 200."
