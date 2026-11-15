# Chapter 1, Crawling as a Distributed System

This directory contains the diagnostic scripts referenced in Chapter 1 of
*SEO for Engineers, Volume 1*. Each script is a working tool you can run
against your own infrastructure to verify the behavior the chapter
describes.

## Setup

The scripts in this chapter are Python. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Scripts

### `ttfb-benchmark.sh`

Measures Time to First Byte and the underlying connection breakdown (DNS,
TCP, TLS) for a single URL, as Googlebot might experience it. Use this
when investigating slow crawl rates or before a deployment that changes
origin response behavior.

Usage:
./ttfb-benchmark.sh https://yourdomain.com/your-page

The output includes the HTTP status, since a fast 404 or 5xx is not a
fast page. Each time is measured from the start of the request, so TLS
includes DNS and TCP. If the request fails outright, the script exits 2
instead of printing zero timings.

A TTFB below 200ms is a reasonable target for crawl efficiency. Above
500ms should be treated as a crawl performance issue worth engineering
attention. See Chapter 1, *The Role of DNS, TCP, and TTFB in Crawling*.

### `http2-check.sh`

Verifies whether an origin is serving HTTP/2 when a client requests it.
Use this when validating CDN configuration changes, or when checking
whether an upstream is still serving HTTP/1.1 to Googlebot.

Usage:
./http2-check.sh https://yourdomain.com

Exits 0 if HTTP/2 was negotiated, 1 if the origin answered over another
protocol, and 2 if the request failed (so an outage is not reported as
"no HTTP/2").

### `verify-googlebot.sh`

Verifies a single connecting IP is genuinely from Googlebot, using
reverse and forward DNS lookups. This is the procedure documented by
Google. Use it for ad-hoc verification, log spot-checks, or when
investigating a suspicious crawl pattern.

Usage:
./verify-googlebot.sh 66.249.66.1

Exits 0 when the IP is verified and 1 when it is not (no reverse DNS, a
non-Google hostname, or a forward lookup that doesn't return the IP).
Exits 2 when `dig` is missing or a DNS query fails, so a resolver outage
is not mistaken for a spoofed crawler in a pipeline.

### `verify-googlebot-ip.py`

The modern approach for verifying Googlebot at scale. Instead of running
a reverse DNS lookup per request, this script downloads Google's
published JSON files of crawler IP ranges and checks whether a given IP
falls inside any of them. It checks two lists: `common-crawlers.json`
(Googlebot and the other crawlers that obey robots.txt, where the old
`googlebot.json` URL now redirects) and `special-crawlers.json` (such as
AdsBot). User-triggered fetchers are deliberately not checked.
IPv4-mapped IPv6 addresses (`::ffff:66.249.66.1`), which dual-stack
servers often write to logs, are matched against the IPv4 ranges.

Exits 0 on a match and 1 when every list was fetched and none matched.
Exits 2 when the result is indeterminate, meaning a list could not be
fetched and no other list matched, or the argument is not a valid IP.

For production use, cache the JSON files locally and refresh on a
schedule. Calling the JSON endpoints on every request is wasteful and
will eventually be rate-limited.

Usage:
python verify-googlebot-ip.py 66.249.66.1
python3 verify-googlebot-ip.py 66.249.66.1

Requires Python 3.10 or later. Uses only the standard library, with an
optional dependency on `certifi` to work around macOS Python.org builds
that ship without a system trust store (install with `pip install certifi`
or `pip3 install certifi`).

## Tests

Unit tests for `verify-googlebot-ip.py` and behavior tests for the shell
scripts live in `tests/`. The Python tests mock all network calls, and
the shell tests put stub `dig` and `curl` commands first on `PATH`, so
the whole suite runs offline. The stubs also simulate failures such as
resolver timeouts and unreachable hosts.

After completing Setup, run them from this directory:

```bash
python3 -m pytest -q
```

Or from the repo root via the top-level Makefile:

```bash
make test-chapter-01-crawling      # pytest suite (Python and shell behavior)
make test-sh-chapter-01-crawling   # bash -n syntax check
```

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.