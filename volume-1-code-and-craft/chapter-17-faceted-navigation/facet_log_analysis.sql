-- facet_log_analysis.sql
--
-- Reference queries for measuring faceted navigation crawl distribution
-- from Chapter 17 of SEO for Engineers, Volume 1.
--
-- These queries assume a BigQuery table `access_logs` with at least:
--   request_uri  STRING   the URL path plus query string
--   user_agent   STRING   the User-Agent header
--   request_date DATE     the date of the request
--   status_code  INT64    the HTTP response status
--
-- Adjust column names to match your schema. The patterns generalize
-- to any SQL dialect that supports regexp_contains or a regex
-- equivalent (Postgres ~ , MySQL REGEXP , Snowflake REGEXP_LIKE).
--
-- For verified-Googlebot-only analysis, filter on a separate
-- verified_user_agent column produced by the Chapter 16
-- verify-googlebot.py script, rather than the raw user_agent.


-- Query 1, monthly URL-class distribution
--
-- This is the chapter's main diagnostic. It tells you what
-- percentage of Googlebot's requests went to URLs that you
-- classify as wasted (tracking, sort, pagination, multi-facet,
-- single-facet) versus clean canonical URLs. If multi_facet and
-- single_facet dominate, your facet treatment is not working.

SELECT
  CASE
    WHEN regexp_contains(request_uri, r'\butm_')         THEN 'tracking'
    WHEN regexp_contains(request_uri, r'\bsessionid=')   THEN 'session'
    WHEN regexp_contains(request_uri, r'\bsid=')         THEN 'session'
    WHEN regexp_contains(request_uri, r'\bsort=')        THEN 'sort'
    WHEN regexp_contains(request_uri, r'\bper_page=')    THEN 'per_page'
    WHEN regexp_contains(request_uri, r'\bview=')        THEN 'view'
    WHEN regexp_contains(request_uri, r'\bpage=')        THEN 'pagination'
    WHEN regexp_contains(request_uri, r'\?.*=.*&.*=')    THEN 'multi_facet'
    WHEN regexp_contains(request_uri, r'\?[^=]+=')       THEN 'single_facet'
    ELSE 'clean_url'
  END AS url_class,
  COUNT(*) AS requests,
  COUNT(DISTINCT request_uri) AS unique_urls,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent_of_total
FROM access_logs
WHERE
  user_agent LIKE '%Googlebot%'
  AND request_date BETWEEN '2026-03-01' AND '2026-03-31'
GROUP BY url_class
ORDER BY requests DESC;


-- Query 2, weekly trend of clean vs wasted crawl
--
-- The same classification rolled up by week. Use this to track
-- whether facet treatment is improving or degrading after a deploy.
-- A successful Tier 1 promotion should show clean_url and
-- single_facet share rising; a regression shows multi_facet share
-- climbing.

SELECT
  DATE_TRUNC(request_date, WEEK) AS week,
  CASE
    WHEN regexp_contains(request_uri, r'\butm_|\bsessionid=|\bsid=') THEN 'wasted'
    WHEN regexp_contains(request_uri, r'\?.*=.*&.*=')                THEN 'multi_facet'
    WHEN regexp_contains(request_uri, r'\?[^=]+=')                   THEN 'single_facet'
    ELSE 'clean_url'
  END AS url_class,
  COUNT(*) AS requests
FROM access_logs
WHERE
  user_agent LIKE '%Googlebot%'
  AND request_date BETWEEN '2026-01-01' AND '2026-12-31'
GROUP BY week, url_class
ORDER BY week, url_class;


-- Query 3, top wasted URL patterns
--
-- When you see a high multi_facet share in Query 1, this query
-- tells you which specific URL patterns are responsible. Strip the
-- query string to aggregate by path, then list the top patterns by
-- crawl volume. The output is the prioritized worklist for facet
-- registry cleanup or robots.txt additions.

SELECT
  REGEXP_EXTRACT(request_uri, r'^([^?]+)') AS path,
  COUNT(*) AS requests,
  COUNT(DISTINCT request_uri) AS unique_urls_with_params
FROM access_logs
WHERE
  user_agent LIKE '%Googlebot%'
  AND request_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND regexp_contains(request_uri, r'\?[^=]+=')
GROUP BY path
ORDER BY requests DESC
LIMIT 50;


-- Query 4, response-code distribution for facet URLs
--
-- The Cross-Role Implications section warns that empty-result
-- facet pages should return 404, not 200. This query verifies the
-- production behavior. Facet URLs returning 200 with low content
-- size are soft-404 candidates and should be investigated.

SELECT
  status_code,
  COUNT(*) AS requests,
  ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent_of_total
FROM access_logs
WHERE
  user_agent LIKE '%Googlebot%'
  AND request_date BETWEEN '2026-03-01' AND '2026-03-31'
  AND regexp_contains(request_uri, r'\?[^=]+=')
GROUP BY status_code
ORDER BY requests DESC;