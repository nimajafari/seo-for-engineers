#!/usr/bin/env bash
#
# verify-googlebot.sh
#
# Verify a connecting IP is genuinely from Googlebot, using reverse and
# forward DNS lookups. This is the procedure documented by Google.
#
# Usage:
#   ./verify-googlebot.sh 66.249.66.1
#
# Exit codes:
#   0  the IP passes verification
#   1  the IP is not a verified Googlebot (no PTR, wrong domain, or the
#      forward lookup does not return the IP)
#   2  indeterminate: dig is missing or a DNS query failed (timeout,
#      SERVFAIL), so a resolver outage is not misread as a spoof
#
# Reference: SEO for Engineers, Volume 1, Chapter 1.
# Google docs:
#   https://developers.google.com/crawling/docs/crawlers-fetchers/verify-google-requests
#

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <ip>" >&2
  exit 1
fi

IP="$1"

if ! command -v dig >/dev/null 2>&1; then
  echo "dig is not installed (dnsutils / bind-tools)" >&2
  exit 2
fi

# Run dig +short and fail with exit 2 on a query error. dig exits 0 for
# NXDOMAIN and empty answers (a real "no record"), and non-zero for
# timeouts and unreachable resolvers, which it also reports on stdout as
# ";;" comment lines that must not be mistaken for answers.
lookup() {
  local out
  if ! out=$(dig +short "$@" 2>&1); then
    echo "DNS query failed (dig $*): $out" >&2
    exit 2
  fi
  printf '%s\n' "$out" | grep -v '^;;' || true
}

# Step 1: Reverse DNS on the connecting IP.
PTR=$(lookup -x "$IP")
HOST=$(printf '%s\n' "$PTR" | sed -n '1s/\.$//p')
if [ -z "$HOST" ]; then
  echo "No reverse DNS record for $IP"
  exit 1
fi
echo "Reverse DNS: $HOST"

# Step 2: Check that the hostname ends in googlebot.com or google.com.
if [[ "$HOST" != *.googlebot.com && "$HOST" != *.google.com ]]; then
  echo "Hostname does not end in googlebot.com or google.com. Not a verified Googlebot."
  exit 1
fi

# Step 3: Forward DNS on the returned hostname, and check the original IP
# is among the resolved addresses. Query both A and AAAA records: a host
# can have several addresses, and Googlebot also crawls over IPv6, so a
# single first-A check (`head -1`) would falsely reject either case.
FORWARD_IPS=$(lookup A "$HOST"; lookup AAAA "$HOST")
echo "Forward DNS:"
printf '%s\n' "$FORWARD_IPS" | sed 's/^/  /'

if printf '%s\n' "$FORWARD_IPS" | grep -qxF "$IP"; then
  echo "OK, verified Googlebot ($IP)"
  exit 0
else
  echo "Forward DNS does not match. Possible spoof."
  exit 1
fi