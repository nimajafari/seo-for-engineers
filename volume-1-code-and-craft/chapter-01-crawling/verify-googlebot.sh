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
# Exits 0 if the IP passes verification, 1 otherwise.
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

# Step 1: Reverse DNS on the connecting IP.
HOST=$(dig +short -x "$IP" | sed 's/\.$//')
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

# Step 3: Forward DNS on the returned hostname, and check it resolves
# back to the original IP.
FORWARD_IP=$(dig +short "$HOST" | head -1)
echo "Forward DNS: $FORWARD_IP"

if [ "$FORWARD_IP" = "$IP" ]; then
  echo "OK, verified Googlebot ($IP)"
  exit 0
else
  echo "Forward DNS does not match. Possible spoof."
  exit 1
fi