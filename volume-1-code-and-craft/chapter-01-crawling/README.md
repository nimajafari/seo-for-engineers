# Chapter 1, Crawling as a Distributed System

This directory contains the diagnostic scripts referenced in Chapter 1 of
*SEO for Engineers, Volume 1*. Each script is a working tool you can run
against your own infrastructure to verify the behavior the chapter
describes.

## Scripts

### `ttfb-benchmark.sh`

Measures Time to First Byte and the underlying connection breakdown (DNS,
TCP, TLS) for a single URL, as Googlebot might experience it. Use this
when investigating slow crawl rates or before a deployment that changes
origin response behavior.

Usage:
./ttfb-benchmark.sh https://yourdomain.com/your-page

A TTFB below 200ms is a reasonable target for crawl efficiency. Above
500ms should be treated as a crawl performance issue worth engineering
attention. See Chapter 1, *The Role of DNS, TCP, and TTFB in Crawling*.

### `http2-check.sh`

Verifies whether an origin is serving HTTP/2 when a client requests it.
Use this when validating CDN configuration changes, or when checking
whether an upstream is still serving HTTP/1.1 to Googlebot.

Usage:
./http2-check.sh https://yourdomain.com

### `verify-googlebot.sh`

Verifies a single connecting IP is genuinely from Googlebot, using
reverse and forward DNS lookups. This is the procedure documented by
Google. Use it for ad-hoc verification, log spot-checks, or when
investigating a suspicious crawl pattern.

Usage:
./verify-googlebot.sh 66.249.66.1

Returns exit code 0 on success and a non-zero exit code on failure, so
the script can be used in pipelines.

### `verify-googlebot-ip.py`

The modern approach for verifying Googlebot at scale. Instead of running
a reverse DNS lookup per request, this script downloads Google's
published JSON files of crawler IP ranges and checks whether a given IP
falls inside any of them.

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

Unit tests for `verify-googlebot-ip.py` and syntax checks for the shell
scripts live in `tests/`. The Python tests mock all network calls, so the
suite runs offline.

Run them from this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest -q
```

Or from the repo root via the top-level Makefile:

```bash
make test-chapter-01-crawling      # pytest suite
make test-sh-chapter-01-crawling   # bash -n syntax check
```

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.