# Chapter 18, Log File Analysis for Backend Engineers

This directory contains the production pipeline and analytical
queries referenced in Chapter 18 of *SEO for Engineers, Volume 1*.
The artifacts here implement the chapter's central recommendation:
treat crawler logs as a first-class observability signal, enriched
once and queried many times, with verified crawler identity as a
column on every log line.

Five artifacts cover the chapter's full pipeline. The enrichment
script and multi-bot verifier are the production shipping core. The
log parser handles the format conversion most teams need before they
can use either. The SQL queries are the analytical layer, ready to
run against any standard log table. Each piece maps to a specific
section of the chapter, so a reader can trace any artifact back to
the prose that motivates it.

Upstream of all of them, the [`log-formats/`](log-formats/) configs
ship the recommended server log formats that produce the logs
`parse_logs.py` consumes, because none of this works if the logs
aren't captured correctly in the first place.

## Producing the logs (`log-formats/`)

Before any analysis is possible, the server has to emit logs in a
format that carries the fields SEO analysis needs. Section 18.2 of
the chapter gives the configs; they ship here as reference snippets:

- **`log-formats/nginx-seo.conf`** — two nginx `log_format` blocks.
  `seo_json` is the recommended one (the chapter's guidance is to
  emit JSON if you are configuring logging today); its keys are
  exactly what `parse_logs.py`'s JSON reader expects. `seo_combined`
  is the legacy Combined-style fallback. Both add `$request_time`
  and `$upstream_response_time` (slow responses to Googlebot reduce
  crawl budget) and use the ISO 8601 `$time_iso8601` timestamp.
- **`log-formats/apache-seo.conf`** — the Apache `LogFormat`
  equivalent, parsed by `parse_logs.py`'s NCSA Combined reader.

These close the loop: the output of these configs is exactly what
`parse_logs.py` reads and normalizes for the rest of the pipeline.

## Scripts

### `parse_logs.py`

A log format converter that reads NCSA Combined, nginx default,
nginx JSON, Apache, AWS ALB, and Cloudflare Logpush formats, and
emits a normalized JSON Lines stream suitable for ingestion by
DuckDB, BigQuery, ClickHouse, or any other engine that consumes
JSON.

The normalized schema is the union of fields Chapter 18 references
across its analytical queries:

| Field          | Type    | Notes                                |
| -------------- | ------- | ------------------------------------ |
| `timestamp`    | string  | ISO 8601 UTC                         |
| `remote_addr`  | string  | client IP                            |
| `method`       | string  | HTTP method                          |
| `host`         | string  | request hostname                     |
| `uri`          | string  | full URI including query string      |
| `path`         | string  | URI with query string stripped       |
| `status`       | integer | HTTP status code                     |
| `bytes_sent`   | integer | response body size                   |
| `referer`      | string  | may be empty                         |
| `user_agent`   | string  | raw User-Agent header                |
| `request_time` | float   | total request time in seconds        |

Usage from the command line:

```bash
# Convert NCSA Combined to JSON Lines (format auto-detected from input)
python parse_logs.py \
  --format combined \
  --input /var/log/nginx/access.log

# Explicit format, gzipped input, write to disk
python parse_logs.py \
  --format nginx_json \
  --input access.log.gz \
  --output normalized.ndjson

# AWS ALB logs from S3 (read with awscli, pipe through)
aws s3 cp s3://my-bucket/AWSLogs/.../access.log.gz - \
  | python parse_logs.py --format alb --input -

# Cloudflare Logpush (already JSON; this normalizes the field names)
python parse_logs.py --format cloudflare --input logpush.ndjson.gz
```

The script handles gzipped input transparently. Format autodetection
inspects the first few lines and picks the parser; pass `--format`
explicitly when autodetection is wrong (most common for ambiguous
custom formats).

Bad lines are logged to stderr with the original content; the script
continues processing the rest of the file. This is intentional. A
malformed line in the middle of a 50 GB log file should not stop
the enrichment.

### `enrich_logs.py`

The DuckDB enrichment pipeline from Chapter 18 section 18.4.2,
productized. Reads normalized JSON Lines (the output of
`parse_logs.py`, or any equivalent format), verifies crawler
identity by IP against published IP ranges, extracts the path from
the URI, and writes compressed Parquet. The enrich-once-query-many
pattern the chapter argues for.

The script:

- Fetches and caches Google, Bing, Apple, OpenAI, and Anthropic
  crawler IP ranges. Cache TTL is 24 hours.
- Adds a `verified_crawler` column (one of `googlebot`,
  `special-crawlers`, `user-triggered-fetchers`, `bingbot`,
  `applebot`, `gptbot`, `oai_searchbot`, `chatgpt_user`,
  `claudebot`, or `''`).
- Adds a `crawler_purpose` column (`search`, `ai_training`,
  `ai_search`, or `''`) so analyses can split search crawlers
  from AI crawlers.
- Adds a `verified_googlebot` boolean (`verified_crawler IN
  ('googlebot', 'special-crawlers')`) for the queries in
  `crawl_analytics.sql`.
- Extracts the `path` from `uri` using a SQL regex, dropping query
  strings, so aggregations group correctly.
- Truncates the last octet of IPv4 (last 80 bits of IPv6) addresses
  after verification, per the chapter's GDPR-conscious anonymization
  pattern in section 18.10.7. Disabled with `--no-anonymize` if you
  need the full IP for incident investigation.
- Computes `verify_crawler(remote_addr)` once per row inside a CTE
  rather than three times in the outer SELECT, so the Python UDF
  fires once per log line, not three times.
- Writes ZSTD-compressed Parquet. A month of mid-size e-commerce
  logs (~10 GB JSON) compresses to ~800 MB.

Usage:

```bash
# Default: read JSON Lines, write Parquet
python enrich_logs.py \
  --input normalized.ndjson \
  --output enriched.parquet

# Process a glob of daily logs
python enrich_logs.py \
  --input 'logs/raw/access-2026-04-*.ndjson.gz' \
  --output logs/enriched/2026-04.parquet

# Keep full IP addresses (incident investigation, scoped access)
python enrich_logs.py \
  --input normalized.ndjson \
  --output enriched.parquet \
  --no-anonymize

# Override the default crawler set
python enrich_logs.py \
  --input normalized.ndjson \
  --output enriched.parquet \
  --crawlers googlebot,bingbot
```

The script depends on `duckdb`, `requests`, and `pyarrow`. Install
with `pip install -r requirements.txt`.

### `verify_crawler.py`

A multi-bot extension of Chapter 16's `verify-googlebot.py`. The
Chapter 16 script handles Google's crawler family. This one extends
the same IP-range verification approach to Bing, Apple, OpenAI, and
Anthropic, which the chapter touches on in section 18.3.

The module exposes:

- `load_all_crawlers(filter=None)` — load IP ranges for every
  registered crawler (or the subset listed in `filter`), with 24-hour
  on-disk caching under `~/.cache/seo-crawler-ranges/`. Returns a
  dict keyed by crawler name.
- `classify_ip(ip, crawlers)` — return the verified crawler name
  that owns `ip`, or `None`.
- `Crawler` dataclass — exposes `.name`, `.purpose`, `.ua_tokens`,
  `.ranges_url`, `.networks`. `enrich_logs.py` reads `.purpose` to
  populate the `crawler_purpose` column.

The crawler registry is opinionated. Each entry records the
published IP-range URL where one exists; entries whose URL is `None`
(Apple, Anthropic at time of writing) register with an empty network
list and a stderr warning so the rest of the pipeline still runs.
Operators who need verification for those crawlers should patch
`_CRAWLER_DEFS` with the URL they obtain out of band.

CLI usage:

```bash
# Filter a log to verified-crawler-only output
python verify_crawler.py \
  --input access.log \
  --output verified.ndjson \
  --format combined

# Report which crawler families are present without filtering
python verify_crawler.py \
  --input access.log \
  --format combined \
  --summary-only

# Restrict to a specific crawler subset
python verify_crawler.py \
  --input access.log \
  --format combined \
  --crawlers googlebot,bingbot
```

For Googlebot-only workflows, Chapter 16's
[`verify-googlebot.py`](../chapter-16-crawl-budget/verify-googlebot.py)
remains the canonical tool. This script is the right choice for
sites that care about AI crawler activity alongside traditional
search crawlers.

### `crawl_analytics.sql`

The six analytical queries from Chapter 18 sections 18.5 through
18.7, parameterized for use against any standard log table schema.
Each query is annotated with the section it corresponds to and the
question it answers.

The queries assume the enriched schema produced by `enrich_logs.py`
loaded as a table named `enriched_logs`:

| Column               | Type                       | Notes                          |
| -------------------- | -------------------------- | ------------------------------ |
| `timestamp`          | timestamp with timezone    | UTC                            |
| `remote_addr`        | string                     | client IP (may be anonymized)  |
| `uri`                | string                     | full URI with query string     |
| `path`               | string                     | URI with query stripped        |
| `status`             | integer                    | HTTP status code               |
| `bytes_sent`         | integer                    | response body size             |
| `request_time`       | float                      | seconds                        |
| `verified_crawler`   | string                     | lowercased crawler name or `''` |
| `verified_googlebot` | boolean                    | derived                        |

The queries are written in DuckDB-compatible SQL. They run as-is on
DuckDB, BigQuery, and Snowflake. PostgreSQL needs a minor adjustment
to `DATE_DIFF` syntax; ClickHouse needs `quantile()` in place of
`APPROX_PERCENTILE`.

Run a single query with DuckDB:

```bash
duckdb -c "$(sed -n '/^-- Query 1/,/^-- Query 2/p' crawl_analytics.sql)"
```

Or load all the queries as views and query them interactively in a
notebook.

### `requirements.txt`

Python dependencies for the three scripts: `duckdb`, `requests`,
and `pyarrow`. All pure-Python or pre-built wheels; no compilation
required.

## Wiring into a daily pipeline

The pipeline shape Chapter 18 argues for is enrich-once,
query-many. A daily cron job reads yesterday's raw logs, normalizes
them, enriches with verified crawler identity, and writes Parquet.
All subsequent analysis reads the Parquet.

```bash
#!/usr/bin/env bash
# /etc/cron.daily/seo-log-enrichment
set -euo pipefail

YESTERDAY=$(date -u -d 'yesterday' +%Y-%m-%d)
RAW_DIR=/var/log/cdn/raw
ENRICHED_DIR=/var/log/cdn/enriched

mkdir -p "${ENRICHED_DIR}/${YESTERDAY}"

# 1. Parse and normalize the raw logs.
python parse_logs.py \
  --format cloudflare \
  --input "${RAW_DIR}/${YESTERDAY}/*.ndjson.gz" \
  --output "${RAW_DIR}/${YESTERDAY}/normalized.ndjson"

# 2. Enrich with verified crawler identity.
python enrich_logs.py \
  --input "${RAW_DIR}/${YESTERDAY}/normalized.ndjson" \
  --output "${ENRICHED_DIR}/${YESTERDAY}/enriched.parquet"

# 3. Run the analytical queries that produce the dashboard data.
duckdb -csv \
  -c ".read crawl_analytics.sql" \
  "${ENRICHED_DIR}/${YESTERDAY}/enriched.parquet" \
  > "${ENRICHED_DIR}/${YESTERDAY}/metrics.csv"

# 4. Ship the metrics CSV to your dashboard backend.
curl -X POST https://metrics.internal/seo \
  -H 'Content-Type: text/csv' \
  --data-binary "@${ENRICHED_DIR}/${YESTERDAY}/metrics.csv"

# 5. Delete raw logs after enrichment; keep the enriched Parquet.
rm -rf "${RAW_DIR}/${YESTERDAY}"
```

For sites operating at the cloud-scale tier the chapter describes
in 18.4.3 (BigQuery, Athena, ClickHouse), the same pattern applies:
ingest into the warehouse, enrich at ingestion via a transform
step, and run the analytical queries on the enriched table.

## Primary sources

The scripts and the chapter both reference the same primary
sources. See the top-level [`CITATIONS.md`](../../CITATIONS.md) for
the full list.
