# Chapter 16, Crawl Budget

This directory contains the diagnostic and remediation scripts
referenced in Chapter 16 of *SEO for Engineers, Volume 1*. The
scripts cover the three operations the chapter argues every
large-site engineering team should be doing routinely. Verifying
that Googlebot traffic in your logs is actually Googlebot,
analyzing the verified traffic to identify crawl waste patterns,
and stripping tracking parameters at the edge so the waste never
accumulates in the first place.

## Scripts

### `verify-googlebot.py`

A Python script that filters a server access log down to verified
Googlebot requests. Verification follows Google's published method:
the request's source IP must fall within Google's published IP
ranges for crawlers, and the request's `User-Agent` header must
contain a recognized Googlebot product token. Either check alone is
insufficient. Spoofed user-agents from arbitrary IPs are common,
and legitimate Chrome users routed through Google proxies request
from Googlebot IPs without being crawlers.

The script:

- Fetches the current Googlebot IP ranges from
  `developers.google.com/search/apis/ipranges/googlebot.json`.
- Parses each log line, extracting client IP and `User-Agent`.
- Emits only the lines where both the IP is in the published
  ranges and the `User-Agent` matches a known Googlebot token.
- Reports a summary of accepted vs rejected lines, broken down by
  rejection reason (IP not in ranges, UA not Googlebot, both).

The IP ranges are cached locally for 24 hours to avoid hammering
Google's endpoint on every run. The cache location is configurable.

Usage.
Verify a log file, output to stdout
python verify-googlebot.py --log /var/log/nginx/access.log
Verify a log file, write filtered output to disk and a summary to stderr
python verify-googlebot.py
--log /var/log/nginx/access.log
--output /tmp/verified-googlebot.log
Force a refresh of the cached IP ranges
python verify-googlebot.py
--log /var/log/nginx/access.log
--refresh-ranges
Use explicit field indexes for a custom log format
python verify-googlebot.py
--log /var/log/nginx/access.log
--ip-field 1
--ua-field 12
Print only the summary, no log output
python verify-googlebot.py
--log /var/log/nginx/access.log
--summary-only

The script handles common log formats (NCSA combined, common log
format, Apache, nginx default) out of the box and supports gzipped
input transparently. For custom log formats, pass `--ip-field` and
`--ua-field` as 1-indexed field positions after whitespace tokenization.

The other Googlebot family bots (Googlebot-Image, Googlebot-News,
Googlebot-Video, Storebot, AdsBot, etc.) are recognized by default.
Pass `--strict-googlebot` to restrict to the primary web crawler
token only.

Install.
pip install -r requirements.txt

### `crawl-waste-analyzer.py`

A Python script that consumes a verified Googlebot log (the output
of `verify-googlebot.py`) and produces the standard crawl-waste
diagnostic report from Chapter 16. The script materializes in code
what the chapter's three `awk` queries describe in shell.

The report covers:

- **Status code distribution.** What percentage of Googlebot
  requests returned `200`, `304`, `404`, `410`, `3xx`, `5xx`?
- **Top URL patterns by crawl volume.** Query strings are
  stripped, so all variants of `/products/widget` aggregate under
  a single bucket. The top *N* patterns are reported.
- **Parameter frequency.** Every URL parameter Googlebot
  encountered is counted across all crawls. This is the chapter's
  "first time most teams run it, they find parameters they did
  not know existed" query.
- **Asset-path crawl share.** What fraction of crawl volume is
  going to paths that look like CSS, JS, image, or framework
  assets? A high number is fine, a high number with high asset
  TTFB is a sign Googlebot is being routed past a cache.
- **Soft-`404` candidates.** URLs returning `200` with response
  sizes that fall below a configurable threshold. Empty category
  or search pages typically show up here.
- **Redirect chain estimate.** For each requesting URL, count the
  ratio of `3xx` responses to total requests. A high ratio means
  Googlebot is spending crawl budget walking redirects.
- **Per-URL-pattern TTFB.** If response times are available in the
  log (most production formats include them), the script reports
  p50 and p95 TTFB per top URL pattern. Patterns with significantly
  higher TTFB than the site average are crawl-capacity drags.

The output is JSON, structured for ingestion into dashboards or
CI assertions. A human-readable summary is also printed to stderr.

Usage.
Analyze a verified Googlebot log
python crawl-waste-analyzer.py --log /tmp/verified-googlebot.log
Adjust the top-N for URL patterns and parameters
python crawl-waste-analyzer.py
--log /tmp/verified-googlebot.log
--top-patterns 100
--top-parameters 50
Set the soft-404 threshold in bytes
python crawl-waste-analyzer.py
--log /tmp/verified-googlebot.log
--soft-404-threshold 2048
Specify which log fields contain status, URL, size, and response time
python crawl-waste-analyzer.py
--log /tmp/verified-googlebot.log
--status-field 9
--url-field 7
--size-field 10
--rtime-field 11
Write the JSON report to disk
python crawl-waste-analyzer.py
--log /tmp/verified-googlebot.log
--output /tmp/crawl-waste-report.json

The script does not make policy recommendations. It produces the
data the chapter's decision framework (the four-question tree
in *Fixing crawl waste*) operates on. Reading the JSON output,
spotting patterns that violate the chapter's healthy-crawl
heuristics, and deciding which remediation tool applies is the
engineer's work.

Install.
pip install -r requirements.txt

### `strip-tracking-params-worker.js`

The Cloudflare Worker from Chapter 16, packaged for direct
deployment. The worker intercepts every request, checks for any
of a configurable list of tracking parameters in the URL
(`utm_*`, `gclid`, `fbclid`, `mc_cid`, etc.), and if present,
issues a `301` redirect to the same URL with those parameters
removed. The canonical, parameterless URL then responds and is
the only URL that accumulates ranking signals.

This is Layer 2 in the chapter's layered remediation strategy.
It does not replace Layer 1 (do not generate tracking parameters
on internal links) and it should be combined with Layer 3
(self-referencing canonicals on the parameterless URL). What it
does is convert the would-be crawl of a parameterized URL into a
crawl of the canonical, without the canonicalization signal needing
to be learned by Google over time.

The parameter list is exposed as a constant at the top of the
file and is easy to extend. Defaults include the standard UTM
parameters, the major ad platform click IDs (`gclid`, `fbclid`,
`msclkid`, `mc_cid`, `mc_eid`), and a handful of widely abused
internal trackers (`ref`, `source`, `_ga`, `_gl`).

Deploy with Wrangler.
npm install -g wrangler
wrangler login
wrangler deploy strip-tracking-params-worker.js --name strip-tracking-params

Then bind the worker to the routes you want to protect in the
Cloudflare dashboard, typically `*.example.com/*`. The worker
adds negligible latency (sub-millisecond on the redirect path,
zero on the pass-through path) because the parameter check is
trivially fast.

The same logic works on other edge platforms (Fastly Compute,
AWS Lambda@Edge, Vercel Edge Functions) with minor syntactic
adjustments. The repo ships only the Cloudflare version because
it is the most common deployment target for this pattern in
practice.

## Wiring into observability

The recommended cadence for these scripts is weekly or monthly,
depending on site scale.

```bash
# Weekly cron job on the log aggregation server.
LOG_DATE=$(date -d "1 week ago" +%Y-%m-%d)

python verify-googlebot.py \
  --log /var/log/nginx/access.log.${LOG_DATE}.gz \
  --output /tmp/googlebot-${LOG_DATE}.log

python crawl-waste-analyzer.py \
  --log /tmp/googlebot-${LOG_DATE}.log \
  --output /tmp/crawl-report-${LOG_DATE}.json

# Ship the report into your observability stack.
curl -X POST https://metrics.example.com/crawl-budget \
  -H "Content-Type: application/json" \
  -d @/tmp/crawl-report-${LOG_DATE}.json
```

For event-driven analysis (alerting when crawl waste exceeds a
threshold within a given window), the JSON output of
`crawl-waste-analyzer.py` is the right input. Define thresholds
for the metrics that matter to your site (top-pattern crawl share,
parameter count, soft-404 candidates) and alert on threshold
crossings.

The Cloudflare Worker is one-and-done. Deploy it once, monitor
the redirect count in Cloudflare's analytics for the first week to
confirm it is firing on the patterns you expect, and leave it.
The maintenance cost is zero unless your tracking parameter list
changes.

## Primary sources

The scripts and the chapter both reference the same primary
sources. See the top-level [`CITATIONS.md`](../../CITATIONS.md)
for the full list.