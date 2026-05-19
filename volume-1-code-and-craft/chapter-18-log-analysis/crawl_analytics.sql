-- crawl_analytics.sql
--
-- The six analytical queries from Chapter 18 sections 18.5 through
-- 18.7, parameterized for use against the enriched log table
-- produced by enrich_logs.py.
--
-- The queries assume a DuckDB-compatible engine. On BigQuery and
-- Snowflake they run as-is. On PostgreSQL, DATE_DIFF needs a
-- syntax tweak. On ClickHouse, replace APPROX_PERCENTILE with
-- quantile().
--
-- Expected schema (from enrich_logs.py):
--   timestamp           timestamp UTC
--   remote_addr         string (anonymized by default)
--   method              string
--   host                string
--   uri                 string, with query string
--   path                string, query stripped
--   status              integer
--   bytes_sent          integer
--   user_agent          string
--   request_time        float, seconds
--   verified_crawler    string, lowercased or empty
--   verified_googlebot  boolean


-- Query 1, crawl frequency per URL (section 18.5.1)
--
-- For each URL, how often does Googlebot crawl it, and when was it
-- last seen? Pages you believe to be important but that have not
-- been crawled in 30+ days are a red flag.

SELECT
    path,
    COUNT(*) AS crawl_count,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen,
    DATE_DIFF('day', MAX(timestamp), CURRENT_DATE) AS days_since_last_crawl
FROM enriched_logs
WHERE verified_googlebot = TRUE
  AND status = 200
  AND timestamp >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY path
ORDER BY crawl_count DESC;


-- Query 2, status code distribution by day (section 18.5.2)
--
-- The overall health of your crawl surface. 2xx should dominate.
-- Spikes in 4xx or 5xx are signals worth alerting on.

SELECT
    DATE_TRUNC('day', timestamp) AS day,
    status,
    COUNT(*) AS requests,
    ROUND(100.0 * COUNT(*) /
          SUM(COUNT(*)) OVER (PARTITION BY DATE_TRUNC('day', timestamp)),
          2) AS pct_of_day
FROM enriched_logs
WHERE verified_googlebot = TRUE
  AND timestamp >= CURRENT_DATE - INTERVAL '14' DAY
GROUP BY 1, 2
ORDER BY 1 DESC, 3 DESC;


-- Query 3, crawl depth distribution (section 18.5.3)
--
-- If the mass of your crawl is at depth 5+, your internal linking
-- is pushing Googlebot away from valuable pages.

SELECT
    array_length(split(trim(path, '/'), '/'), 1) AS depth,
    COUNT(*) AS requests,
    COUNT(DISTINCT path) AS unique_urls
FROM enriched_logs
WHERE verified_googlebot = TRUE
  AND status = 200
  AND timestamp >= CURRENT_DATE - INTERVAL '30' DAY
GROUP BY 1
ORDER BY 1;


-- Query 4, response time to Googlebot (section 18.5.4)
--
-- Slow responses to Googlebot directly reduce effective crawl
-- budget. Compare these percentiles to your user-facing TTFB. If
-- they diverge, Googlebot is hitting a slower path.

SELECT
    DATE_TRUNC('hour', timestamp) AS hour,
    APPROX_PERCENTILE(request_time, 0.50) AS p50,
    APPROX_PERCENTILE(request_time, 0.95) AS p95,
    APPROX_PERCENTILE(request_time, 0.99) AS p99,
    COUNT(*) AS requests
FROM enriched_logs
WHERE verified_googlebot = TRUE
  AND status = 200
  AND timestamp >= CURRENT_DATE - INTERVAL '7' DAY
GROUP BY 1
ORDER BY 1 DESC;


-- Query 5, parameter proliferation (section 18.7.1)
--
-- The single most common source of crawl waste, and the single
-- most useful query for detecting it. Base paths with hundreds of
-- distinct parameter combinations are crawl budget liabilities.

WITH parsed AS (
    SELECT
        regexp_extract(uri, '^([^?]+)', 1) AS path,
        regexp_extract(uri, '\?(.*)$', 1) AS query_string
    FROM enriched_logs
    WHERE verified_googlebot = TRUE
      AND timestamp >= CURRENT_DATE - INTERVAL '30' DAY
)
SELECT
    path,
    COUNT(*) AS total_crawls,
    COUNT(*) FILTER (WHERE query_string IS NOT NULL
                       AND query_string != '') AS parameterized_crawls,
    COUNT(DISTINCT query_string) AS unique_parameter_combinations,
    ROUND(100.0 *
          COUNT(*) FILTER (WHERE query_string IS NOT NULL
                             AND query_string != '') / COUNT(*),
          2) AS pct_parameterized
FROM parsed
GROUP BY path
HAVING COUNT(DISTINCT query_string) > 50
ORDER BY unique_parameter_combinations DESC
LIMIT 100;


-- Query 6, uncrawled important pages (section 18.6)
--
-- The pages you believe to be important (your sitemap) that
-- Googlebot has not crawled in the last 30 days. This is the
-- highest-action-density list in this whole file.
--
-- Assumes a sitemap_snapshot table with a path column and a
-- snapshot_date column.

WITH sitemap_urls AS (
    SELECT path
    FROM sitemap_snapshot
    WHERE snapshot_date = CURRENT_DATE
),
recent_crawls AS (
    SELECT DISTINCT path
    FROM enriched_logs
    WHERE verified_googlebot = TRUE
      AND status IN (200, 304)
      AND timestamp >= CURRENT_DATE - INTERVAL '30' DAY
)
SELECT s.path AS uncrawled_path
FROM sitemap_urls s
LEFT JOIN recent_crawls r ON r.path = s.path
WHERE r.path IS NULL;