# Chapter 15, robots.txt, The Specification Engineers Should Actually Read

This directory contains the diagnostic and testing scripts referenced
in Chapter 15 of *SEO for Engineers, Volume 1*. The scripts implement
the CI-gate and post-deploy patterns the chapter argues every
production `robots.txt` should be protected by. Four artifacts are
provided, in increasing order of fidelity to Googlebot's actual
behavior:

1. **`check-robots-nodejs.mjs`** — a Node.js script using the
   `robots-parser` npm package. The standard choice for teams whose
   CI is already Node-based. Not a perfect match for Googlebot in
   every edge case.
2. **`check-robots-google-parser.sh`** — a Bash script that wraps
   Google's open-source C++ parser
   (`github.com/google/robotstxt`). The highest-fidelity option, but
   requires a one-time C++ build step.
3. **`robots-ci-check.py`** — a Python script with an explicit
   assertion suite, sanity checks (BOM, catch-all `Disallow`,
   blocked asset paths, `Crawl-delay` for Googlebot), and JSON
   output. Designed as the primary pre-deploy CI gate.
4. **`robots-post-deploy-smoke.py`** — a Python script that fetches
   the live `robots.txt` from production after deploy and verifies
   that what is being served matches what was expected. Designed as
   the final step of the deploy pipeline.

All four scripts share the same assertion-suite format
(`tests/robots-tests.yaml`), so adding a new must-be-crawlable or
must-be-blocked URL only requires editing one file.

Two further reference artifacts cover the *generation and serving*
side, which the four scripts above only verify:

5. **`serve-robots-nginx.conf`** — a host-based nginx `map` that ties
   the served `robots.txt` body to the request host, making it
   structurally impossible to serve staging's rules on production.
6. **`robots.txt.j2`** — a defensive Jinja template that fails the
   build loudly on an unrecognized environment rather than falling
   through to `Disallow: /`.

## Choosing between parsers

For most teams, `robots-ci-check.py` plus
`robots-post-deploy-smoke.py` is the recommended pair. The Python
parser is faithful to RFC 9309 and Google's same-token merge
extension, the sanity checks catch the failure modes most likely to
ship, and the post-deploy smoke test catches the catastrophic
pattern (a staging file served on production) that no pre-deploy
gate can detect.

For high-stakes sites where a single misclassified URL is material,
add `check-robots-google-parser.sh` as a periodic verification step
against the live file. Google's open-source parser is the
unambiguous answer to any disputed parsing question for Googlebot,
and running it against production catches the small set of edge
cases the Python and Node parsers handle differently.

The Node.js script is provided for teams whose CI is already
Node-based and who prefer not to add a Python toolchain. It uses
`robots-parser`, the standard npm library, which is well-maintained
but does not implement every Googlebot-specific behavior.

## Scripts

### `check-robots-nodejs.mjs`

A Node.js script that validates a local `robots.txt` against a
hard-coded list of must-be-crawlable and must-be-blocked URLs using
the `robots-parser` npm package. The file is configured for
`https://www.example.com`; edit the URL lists at the top of the
script for your origin.

Usage.
npm install
node check-robots-nodejs.mjs                  # uses public/robots.txt
node check-robots-nodejs.mjs path/to/file     # explicit path

The script exits non-zero on any failure. It runs in well under a
second on a typical `robots.txt`.

### `check-robots-google-parser.sh`

A Bash script that wraps the `robots` binary built from
[github.com/google/robotstxt](https://github.com/google/robotstxt).
The binary takes a `robots.txt` path, a user-agent token, and a URL,
and prints `ALLOWED` or `DISALLOWED`. The script iterates over
hard-coded lists of URLs and fails if any assertion does not match.

Usage.
./check-robots-google-parser.sh                # uses public/robots.txt
./check-robots-google-parser.sh path/to/file   # explicit path

The script exits non-zero on any failure. See *Installing the Google
parser* below for the build step.

### `robots-ci-check.py`

A Python script that validates a `robots.txt` file against an
explicit assertion suite, using a Python port of Google's parsing
rules. The script takes a `robots.txt` file (or fetches a live one
from a URL) and a YAML or JSON test file declaring which URLs must
be crawlable and which must be blocked, for which user-agents.

The script implements the following parser behaviors from RFC 9309
and Google's documented extensions:

- **Group selection.** The crawler selects exactly one group, the
  one whose `User-agent` token most specifically matches its own.
  Same-token duplicate groups are merged. Different tokens, including
  `*`, are not merged.
- **Rule precedence.** Within the selected group, the rule whose
  path pattern has the greatest number of literal characters (after
  wildcard expansion) wins. Ties are broken in favor of `Allow` over
  `Disallow`.
- **Wildcard semantics.** `*` matches zero or more of any character.
  `$` anchors the pattern to the end of the URL path. No other
  characters are special.
- **Empty `Disallow:` is a no-op.** `Disallow: /` blocks everything.
  Patterns without `$` are prefix matches.
- **Sitemap directives.** Parsed but not used for the allow/block
  decision (sitemaps are not user-agent scoped).
- **Comments and whitespace.** `#` introduces a comment. Whitespace
  around directives and values is trimmed.

The script also runs the following sanity checks on the file itself,
independent of the assertion suite.

- The file is well-formed UTF-8 with no BOM (warning, not error).
- No catch-all `Disallow: /` exists under a `User-agent: *` group
  unless explicitly opted in via `--allow-catch-all-disallow`.
- All `Sitemap:` directives are absolute URLs.
- No `Crawl-delay` directive targeted at a Googlebot user-agent
  token (warning: Google does not honor it).
- No CSS, JavaScript, or framework asset path appears to be blocked
  for Googlebot. The script flags `Disallow` rules whose path
  matches `*.css$`, `*.js$`, `/static/`, `/assets/`, `/_next/`,
  `/_nuxt/`, or `/build/` and reports them as warnings.

Usage.
Validate the local file against an assertion suite
python robots-ci-check.py 
--robots public/robots.txt 
--tests tests/robots-tests.yaml
Fetch and validate the live production file
python robots-ci-check.py 
--robots-url https://www.example.com/robots.txt 
--tests tests/robots-tests.yaml
Validate without an assertion suite (sanity checks only)
python robots-ci-check.py --robots public/robots.txt
Allow a deliberate catch-all Disallow (e.g. for a staging origin)
python robots-ci-check.py 
--robots public/robots-staging.txt 
--allow-catch-all-disallow
Write a JSON report for CI dashboard ingestion
python robots-ci-check.py 
--robots public/robots.txt 
--tests tests/robots-tests.yaml 
--output report.json

Assertion suite format. A YAML or JSON file with two top-level keys,
`allowed` and `blocked`, each containing a list of objects with
`user_agent` and `url` fields. See `tests/robots-tests.yaml` for the
shipping example.

The script exits non-zero if any error-severity finding is reported,
which makes it suitable as a pre-deploy gate in CI. Warning-severity
findings (catch-all in staging, blocked asset paths) are reported
but do not fail the build by default; pass `--strict` to promote
warnings to errors.

### `robots-post-deploy-smoke.py`

A Python script that fetches the live `robots.txt` from a production
origin after deploy and verifies that what is being served matches
what was expected. The script is intended to run as the final step
of a deployment pipeline. It exits non-zero if the file is missing,
malformed, or serving the wrong content.

The script implements the following post-deploy assertions.

- **The file is reachable.** HTTP `200` with a body. The script
  reports the HTTP status, the `Content-Type` header, and the
  response size.
- **The `Content-Type` is correct.** The header must be
  `text/plain` (with an optional charset suffix). Other types are
  flagged as warnings because some crawlers handle them
  inconsistently.
- **No redirect chain on the canonical host.** The script asserts
  that the configured production host serves `robots.txt` directly,
  not via redirect. (Redirects from non-canonical hosts to the
  canonical one are allowed and tested separately.)
- **No catch-all `Disallow: /` for Googlebot.** Using the same
  parser as the CI check, the script asserts that Googlebot is
  allowed to crawl the site root. This is the single most important
  post-deploy assertion. It catches the catastrophic-failure
  pattern, a staging file shipping to production.
- **Content hash matches the expected file.** If a `--expected-hash`
  is passed, the SHA-256 of the served file body must match. This
  catches CDN cache poisoning, configuration drift, and accidental
  overwrites.
- **Optional URL assertions.** If an assertion suite is passed, the
  same allowed/blocked checks from the CI script are run against the
  live file.
- **The file is also reachable on non-canonical hosts.** If
  `--also-check` URLs are passed (e.g. the non-`www` apex, an HTTP
  variant), the script asserts each returns either a valid file or
  a `301` redirecting to the canonical host's `robots.txt`.

Usage.
Minimal post-deploy smoke test
python robots-post-deploy-smoke.py 
--robots-url https://www.example.com/robots.txt
Verify the deployed file matches the file in the build artifact
python robots-post-deploy-smoke.py 
--robots-url https://www.example.com/robots.txt 
--expected-hash "$(sha256sum public/robots.txt | awk '{print $1}')"
Run assertion suite against the live file
python robots-post-deploy-smoke.py 
--robots-url https://www.example.com/robots.txt 
--tests tests/robots-tests.yaml
Verify alternative hosts redirect to the canonical robots.txt
python robots-post-deploy-smoke.py 
--robots-url https://www.example.com/robots.txt 
--also-check https://example.com/robots.txt 
--also-check http://example.com/robots.txt

## Installing the Google parser

The `robots` binary used by `check-robots-google-parser.sh` is built
from source. One-time setup, on Linux or macOS:
git clone https://github.com/google/robotstxt.git
cd robotstxt
mkdir build && cd build
cmake -DROBOTS_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release ..
make
sudo cp robots /usr/local/bin/
robots --help

For containerized CI, the simplest approach is a multi-stage
Dockerfile that builds the binary once and copies it into a minimal
runtime image. Example:

```dockerfile
FROM debian:bookworm-slim AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates && \
    rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/google/robotstxt.git /src
WORKDIR /src/build
RUN cmake -DROBOTS_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release .. && make

FROM debian:bookworm-slim
COPY --from=builder /src/build/robots /usr/local/bin/robots
ENTRYPOINT ["robots"]
```

The resulting image is under 100 MB and the parser invocation is
sub-second.

## Wiring into CI

The recommended pipeline shape uses two scripts at two stages.

**Pre-deploy (blocking):**

```yaml
- name: Validate robots.txt before deploy
  run: |
    python chapter-15-robots-txt/robots-ci-check.py \
      --robots public/robots.txt \
      --tests chapter-15-robots-txt/tests/robots-tests.yaml \
      --strict
```

**Post-deploy (blocking):**

```yaml
- name: Verify live robots.txt after deploy
  run: |
    EXPECTED_HASH=$(sha256sum public/robots.txt | awk '{print $1}')
    python chapter-15-robots-txt/robots-post-deploy-smoke.py \
      --robots-url https://www.example.com/robots.txt \
      --expected-hash "$EXPECTED_HASH" \
      --tests chapter-15-robots-txt/tests/robots-tests.yaml \
      --also-check https://example.com/robots.txt
```

The pre-deploy gate catches mistakes in the file content. The
post-deploy gate catches everything that happens between the build
artifact and what Googlebot actually sees: wrong CDN configuration,
wrong host routing, redirect chains, cache poisoning, and the
catch-all `Disallow: /` that ships from staging.

**Optional, periodic verification with Google's parser:**

```yaml
# Run once a day against the live file. Catches edge cases the
# Python parser handles differently from Googlebot.
- name: Verify live robots.txt with Google's parser
  run: |
    curl -sS https://www.example.com/robots.txt > /tmp/live-robots.txt
    chapter-15-robots-txt/check-robots-google-parser.sh /tmp/live-robots.txt
```

The Node.js script (`check-robots-nodejs.mjs`) is a substitute for
`robots-ci-check.py` in Node-first environments. The two are not
both needed.

## Serving robots.txt safely

The scripts above *verify* a `robots.txt`. They do not prevent the
single most expensive failure mode in the chapter: a staging file
(which blocks all crawlers) being served on the production host.
The chapter's structural defense is to stop treating `robots.txt` as
a static file that a build step copies from the wrong environment,
and instead derive its content from the environment itself. These two
reference artifacts implement that defense.

### `serve-robots-nginx.conf`

A host-based nginx `map` that selects the `robots.txt` body from the
request host. The default branch is the restrictive
`User-agent: * / Disallow: /` body, so any host not explicitly
recognized as production (staging, preview, an unexpected internal
hostname) is kept out of the index. The only way to serve a
crawlable body on a host is to list that host explicitly, which makes
shipping staging's rules to production a structural impossibility
rather than a review-discipline problem.

The `robots.txt` `location` returns the mapped body directly,
bypassing application logic and static-file handlers so the endpoint
stays boringly reliable (a `5xx` here makes Googlebot treat the whole
origin as disallowed). nginx interprets the `\n` escapes in the
mapped strings as real newlines, producing a valid multi-line file.

Adapt the `map` block: add every production hostname (apex and `www`)
that should be crawlable, and update the `Sitemap:` URL.

### `robots.txt.j2`

A Jinja template for teams that generate `robots.txt` at build or
request time rather than serving it from nginx. It enumerates the
known non-production environments explicitly and raises on anything
unrecognized, so an unset or misspelled environment variable fails
the build loudly instead of silently falling through to
`Disallow: /`.

`fail` is **not** a built-in Jinja2 function; register it as a global
on the environment before rendering (the template's header comment
shows the three-line setup). Render with the `environment` variable
set, e.g. `render(environment="production")`.

Both files are reference configuration, not runnable scripts, so they
are not part of the `make` smoke-test target for this chapter. Their
content should still flow through the verification scripts above: the
body `serve-robots-nginx.conf` serves, or the file `robots.txt.j2`
renders, is exactly what `robots-ci-check.py` and
`robots-post-deploy-smoke.py` should be pointed at.

## Primary sources

The scripts and the chapter both reference the same primary sources.
See the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full
list.