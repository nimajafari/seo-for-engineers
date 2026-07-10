#!/usr/bin/env python3
"""
link-graph-analyzer.py

Build the directed graph of a site's internal links from a crawl
export CSV, compute the structural metrics Chapter 10 of SEO for
Engineers, Volume 1, identifies as actionable, and emit a JSON
report.

The crawl export CSV must have at least two columns, 'source' and
'destination'. An 'anchor' column is read if present but is not
required.

Optionally cross-reference the graph against a sitemap to find pages
that exist in the sitemap but have no inbound internal links in the
crawl. These are sitemap-only orphans, a common engineering failure
described in Chapter 10.

Usage:
    python link-graph-analyzer.py --crawl crawl-export.csv \\
      --homepage https://example.com/

    python link-graph-analyzer.py --crawl crawl-export.csv \\
      --homepage https://example.com/ --sitemap https://example.com/sitemap.xml

    python link-graph-analyzer.py --crawl crawl-export.csv \\
      --homepage https://example.com/ --pagerank --output report.json

    python link-graph-analyzer.py --crawl crawl-export.csv \\
      --homepage https://example.com/ --pagerank \\
      --output report.json --html report.html

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 10.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx
import requests
from lxml import etree

REQUEST_TIMEOUT_SECONDS = 30
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

DEPTH_WARN_THRESHOLD = 3  # Chapter 10's conventional warning threshold


def build_graph(crawl_export_path: Path) -> nx.DiGraph:
    """
    Build a directed graph from a crawler export CSV.

    The CSV is expected to have ``source_url`` and ``target_url``
    columns at minimum. The legacy column names ``source`` and
    ``destination`` are also accepted for backward compatibility,
    so older exports continue to work. An optional ``anchor`` column
    is preserved on each edge if present.

    The ``source_url`` / ``target_url`` convention matches the column
    names used by Chapter 4's link-graph-audit script, so a single
    crawl export feeds both tools.
    """
    g = nx.DiGraph()

    with open(crawl_export_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])

        # Pick the source column. Prefer the canonical name; accept
        # the legacy alias.
        if "source_url" in fields:
            source_col = "source_url"
        elif "source" in fields:
            source_col = "source"
        else:
            raise ValueError(
                "Crawl export must have a 'source_url' (or legacy "
                f"'source') column. Found columns: {reader.fieldnames}"
            )

        # Same for the target column.
        if "target_url" in fields:
            target_col = "target_url"
        elif "destination" in fields:
            target_col = "destination"
        else:
            raise ValueError(
                "Crawl export must have a 'target_url' (or legacy "
                f"'destination') column. Found columns: {reader.fieldnames}"
            )

        for row in reader:
            source = (row.get(source_col) or "").strip()
            destination = (row.get(target_col) or "").strip()
            if not source or not destination:
                continue
            anchor = (row.get("anchor") or "").strip()
            g.add_edge(source, destination, anchor=anchor)

    return g


def parse_sitemap(sitemap_url: str) -> set[str]:
    """Parse a sitemap or sitemap index, return the union of URLs."""
    urls: set[str] = set()
    try:
        response = requests.get(
            sitemap_url,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
    except Exception as exc:
        print(
            f"WARN: failed to fetch sitemap {sitemap_url}: {exc}",
            file=sys.stderr,
        )
        return urls

    try:
        # Sitemaps come from arbitrary, possibly untrusted URLs. Disable
        # entity resolution and network access so a hostile sitemap cannot
        # mount an XXE or billion-laughs entity-expansion attack.
        parser = etree.XMLParser(
            resolve_entities=False, no_network=True, dtd_validation=False
        )
        root = etree.fromstring(response.content, parser=parser)
    except Exception as exc:
        print(
            f"WARN: failed to parse sitemap {sitemap_url}: {exc}",
            file=sys.stderr,
        )
        return urls

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    if root.tag.endswith("sitemapindex"):
        for child in root.findall("sm:sitemap", ns):
            loc = child.find("sm:loc", ns)
            if loc is not None and loc.text:
                urls |= parse_sitemap(loc.text.strip())
        return urls

    for child in root.findall("sm:url", ns):
        loc = child.find("sm:loc", ns)
        if loc is not None and loc.text:
            urls.add(loc.text.strip())

    return urls


def depth_distribution(depths: dict[str, int]) -> dict[str, int]:
    """Bucket pages by depth, with 5+ collapsed."""
    buckets: Counter[str] = Counter()
    for d in depths.values():
        if d == 0:
            buckets["0 (homepage)"] += 1
        elif d == 1:
            buckets["1"] += 1
        elif d == 2:
            buckets["2"] += 1
        elif d == 3:
            buckets["3"] += 1
        elif d == 4:
            buckets["4"] += 1
        else:
            buckets["5+"] += 1
    return dict(buckets)


def resolve_homepage(g: nx.DiGraph, homepage: str) -> str:
    """
    Match the supplied homepage URL against the graph's node keys.

    Crawl exports are inconsistent about the trailing slash on the
    root URL: ``https://example.com`` and ``https://example.com/``
    are the same page but distinct strings, so a literal ``in`` check
    silently misses the homepage and skips all depth metrics. Try the
    URL as given, then with the trailing slash toggled, and return the
    variant that is actually a node so depth analysis can proceed.
    """
    if homepage in g:
        return homepage
    toggled = homepage[:-1] if homepage.endswith("/") else homepage + "/"
    if toggled in g:
        return toggled
    return homepage


def analyze(
    g: nx.DiGraph,
    homepage: str,
    sitemap_urls: set[str] | None = None,
    compute_pagerank: bool = False,
    top_n: int = 20,
) -> dict[str, Any]:
    """Run the full Chapter 10 analysis suite."""
    requested_homepage = homepage
    homepage = resolve_homepage(g, homepage)
    report: dict[str, Any] = {
        "homepage": homepage,
        "total_pages_in_graph": g.number_of_nodes(),
        "total_internal_links": g.number_of_edges(),
        "homepage_present_in_graph": homepage in g,
    }
    if homepage != requested_homepage:
        report["homepage_requested"] = requested_homepage
        report["homepage_note"] = (
            "Requested homepage was not an exact node; matched by "
            "toggling the trailing slash."
        )

    # Orphans by graph definition, nodes with zero in-degree.
    orphans_zero_inbound = sorted(
        n for n in g.nodes()
        if g.in_degree(n) == 0 and n != homepage
    )
    report["orphans_zero_inbound_count"] = len(orphans_zero_inbound)
    report["orphans_zero_inbound"] = orphans_zero_inbound[:200]  # cap for sanity

    # Click depth from homepage.
    if homepage in g:
        depths = nx.single_source_shortest_path_length(g, homepage)
        depth_values = list(depths.values())

        if depth_values:
            report["max_click_depth"] = max(depth_values)
            report["avg_click_depth"] = round(
                sum(depth_values) / len(depth_values), 3
            )
        else:
            report["max_click_depth"] = 0
            report["avg_click_depth"] = 0

        report["depth_distribution"] = depth_distribution(depths)

        reachable = set(depths.keys())
        all_pages = set(g.nodes())
        unreachable = sorted(all_pages - reachable)
        report["unreachable_from_homepage_count"] = len(unreachable)
        report["unreachable_from_homepage"] = unreachable[:200]

        # Pages above the warning depth threshold.
        deep_pages = sorted(
            (n for n, d in depths.items() if d > DEPTH_WARN_THRESHOLD),
            key=lambda x: depths[x],
            reverse=True,
        )
        report["pages_deeper_than_threshold"] = {
            "threshold": DEPTH_WARN_THRESHOLD,
            "count": len(deep_pages),
            "examples": [
                {"url": n, "depth": depths[n]} for n in deep_pages[:50]
            ],
        }

        # Percentage of indexable pages at or below depth 3.
        pages_at_or_below_3 = sum(1 for d in depth_values if d <= 3)
        report["percent_at_or_below_depth_3"] = (
            round(100 * pages_at_or_below_3 / len(depth_values), 2)
            if depth_values
            else 0
        )
    else:
        report["depth_analysis"] = (
            "Homepage not present in crawl graph, depth metrics skipped."
        )

    # Top pages by in-degree, the most internally linked.
    in_degree_sorted = sorted(g.in_degree(), key=lambda x: x[1], reverse=True)
    report["top_pages_by_inlinks"] = [
        {"url": u, "inlinks": d} for u, d in in_degree_sorted[:top_n]
    ]

    # Top pages by out-degree, the most outbound internal links.
    out_degree_sorted = sorted(g.out_degree(), key=lambda x: x[1], reverse=True)
    report["top_pages_by_outlinks"] = [
        {"url": u, "outlinks": d} for u, d in out_degree_sorted[:top_n]
    ]

    # Sitemap-vs-graph diff if a sitemap was provided.
    if sitemap_urls is not None:
        graph_nodes = set(g.nodes())
        sitemap_only = sorted(sitemap_urls - graph_nodes)
        graph_only = sorted(graph_nodes - sitemap_urls)
        report["sitemap_diff"] = {
            "sitemap_url_count": len(sitemap_urls),
            "in_sitemap_only_count": len(sitemap_only),
            "in_sitemap_only": sitemap_only[:200],
            "in_graph_only_count": len(graph_only),
            "in_graph_only": graph_only[:200],
        }

    # Optional PageRank computation.
    if compute_pagerank:
        try:
            pr = nx.pagerank(g, alpha=0.85)
            top_pr = sorted(pr.items(), key=lambda x: x[1], reverse=True)
            report["top_pages_by_pagerank"] = [
                {"url": u, "pagerank": round(v, 6)} for u, v in top_pr[:top_n]
            ]
        except Exception as exc:
            report["pagerank_error"] = str(exc)

    return report


# The visualization is a single self-contained HTML file: the report
# JSON is injected into the page and rendered entirely client-side, so
# the output has no external dependencies and opens straight from disk.
# The ``__REPORT_DATA__`` token is replaced with the report JSON.
HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Internal Linking Report</title>
<style>
  :root {
    --bg:#eef1f5; --surface:#fff; --surface-2:#f6f8fb; --ink:#141b24; --ink-2:#47566a; --ink-3:#7d8da0;
    --line:#dde3ec; --line-strong:#c6d0dd; --accent:#0b96a8; --accent-soft:#d6f0f3;
    --good:#1f9d6b; --good-soft:#d7f0e5; --warn:#c98416; --warn-soft:#f6e9d0; --crit:#d0492f; --crit-soft:#f6dcd5;
    --shadow:0 1px 2px rgba(20,27,36,.04),0 4px 14px rgba(20,27,36,.05);
    --mono:ui-monospace,"SF Mono","JetBrains Mono",Menlo,Consolas,monospace;
    --sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg:#0b1016; --surface:#121a23; --surface-2:#0e161e; --ink:#e8eef6; --ink-2:#a3b1c2; --ink-3:#6b7b8f;
      --line:#22303d; --line-strong:#2e3f4f; --accent:#33c6d8; --accent-soft:#10333a;
      --good:#3ad19a; --good-soft:#123328; --warn:#e3b256; --warn-soft:#33290f; --crit:#f0765c; --crit-soft:#351712;
      --shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);
    }
  }
  :root[data-theme="light"]{--bg:#eef1f5;--surface:#fff;--surface-2:#f6f8fb;--ink:#141b24;--ink-2:#47566a;--ink-3:#7d8da0;--line:#dde3ec;--line-strong:#c6d0dd;--accent:#0b96a8;--accent-soft:#d6f0f3;--good:#1f9d6b;--good-soft:#d7f0e5;--warn:#c98416;--warn-soft:#f6e9d0;--crit:#d0492f;--crit-soft:#f6dcd5;--shadow:0 1px 2px rgba(20,27,36,.04),0 4px 14px rgba(20,27,36,.05);}
  :root[data-theme="dark"]{--bg:#0b1016;--surface:#121a23;--surface-2:#0e161e;--ink:#e8eef6;--ink-2:#a3b1c2;--ink-3:#6b7b8f;--line:#22303d;--line-strong:#2e3f4f;--accent:#33c6d8;--accent-soft:#10333a;--good:#3ad19a;--good-soft:#123328;--warn:#e3b256;--warn-soft:#33290f;--crit:#f0765c;--crit-soft:#351712;--shadow:0 1px 2px rgba(0,0,0,.3),0 6px 20px rgba(0,0,0,.35);}
  *{box-sizing:border-box;}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);line-height:1.5;-webkit-font-smoothing:antialiased;}
  .wrap{max-width:1080px;margin:0 auto;padding:32px 24px 72px;}
  header.top{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:18px;margin-bottom:8px;}
  .eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:600;}
  h1{font-size:clamp(24px,4vw,36px);line-height:1.05;margin:8px 0 6px;letter-spacing:-.02em;text-wrap:balance;}
  h1 .dom{font-family:var(--mono);font-weight:600;}
  .sub{color:var(--ink-2);font-size:14px;margin:0;}
  .verdict{display:inline-flex;align-items:center;gap:9px;padding:9px 15px;border-radius:999px;font-weight:600;font-size:13px;white-space:nowrap;}
  .verdict.good{background:var(--good-soft);color:var(--good);border:1px solid color-mix(in srgb,var(--good) 30%,transparent);}
  .verdict.warn{background:var(--warn-soft);color:var(--warn);border:1px solid color-mix(in srgb,var(--warn) 30%,transparent);}
  .verdict.crit{background:var(--crit-soft);color:var(--crit);border:1px solid color-mix(in srgb,var(--crit) 30%,transparent);}
  .verdict .dot{width:9px;height:9px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px color-mix(in srgb,currentColor 22%,transparent);}
  .kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:26px 0 30px;}
  .kpi{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:15px 16px;box-shadow:var(--shadow);position:relative;overflow:hidden;}
  .kpi .label{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink-3);font-weight:600;}
  .kpi .val{font-family:var(--mono);font-size:26px;font-weight:600;letter-spacing:-.02em;margin-top:8px;font-variant-numeric:tabular-nums;line-height:1;}
  .kpi .unit{font-size:12px;color:var(--ink-3);font-family:var(--sans);font-weight:500;margin-left:2px;}
  .kpi .foot{font-size:11px;color:var(--ink-2);margin-top:6px;}
  .kpi.state-good::before,.kpi.state-warn::before,.kpi.state-crit::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;}
  .kpi.state-good::before{background:var(--good);}.kpi.state-warn::before{background:var(--warn);}.kpi.state-crit::before{background:var(--crit);}
  .pill{display:inline-block;font-size:10px;font-weight:700;padding:2px 7px;border-radius:999px;letter-spacing:.03em;}
  .pill.good{background:var(--good-soft);color:var(--good);}.pill.warn{background:var(--warn-soft);color:var(--warn);}.pill.crit{background:var(--crit-soft);color:var(--crit);}
  .grid-2{display:grid;grid-template-columns:1.55fr 1fr;gap:20px;align-items:stretch;}
  .card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:var(--shadow);display:flex;flex-direction:column;}
  .card h2{font-size:15px;margin:0 0 3px;letter-spacing:-.01em;}
  .card .hint{font-size:12.5px;color:var(--ink-2);margin:0 0 18px;}
  .ladder{display:flex;flex-direction:column;gap:11px;}
  .rung{display:grid;grid-template-columns:82px 1fr 58px;align-items:center;gap:12px;}
  .rung .tier{font-family:var(--mono);font-size:12px;color:var(--ink-2);font-variant-numeric:tabular-nums;}
  .rung .tier b{color:var(--ink);font-weight:600;}
  .bar-track{background:var(--surface-2);border:1px solid var(--line);border-radius:7px;height:22px;overflow:hidden;}
  .bar-fill{height:100%;border-radius:6px 0 0 6px;background:linear-gradient(90deg,color-mix(in srgb,var(--accent) 78%,transparent),var(--accent));transition:width .8s cubic-bezier(.2,.7,.2,1);}
  .rung.beyond .bar-fill{background:linear-gradient(90deg,color-mix(in srgb,var(--warn) 70%,transparent),var(--warn));}
  .rung .count{font-family:var(--mono);font-size:13px;text-align:right;font-variant-numeric:tabular-nums;color:var(--ink);font-weight:600;}
  .threshold-note{display:flex;align-items:center;gap:8px;margin-top:16px;padding-top:15px;border-top:1px dashed var(--line-strong);font-size:12px;color:var(--ink-2);}
  .swatch{width:11px;height:11px;border-radius:3px;display:inline-block;}
  .reach{display:flex;flex-direction:column;gap:18px;flex:1;min-height:0;}
  .donut-wrap{display:flex;align-items:center;gap:18px;}
  .donut{width:108px;height:108px;border-radius:50%;flex:none;display:grid;place-items:center;background:conic-gradient(var(--good) calc(var(--pct)*1%),var(--surface-2) 0);position:relative;}
  .donut::after{content:"";position:absolute;inset:13px;border-radius:50%;background:var(--surface);border:1px solid var(--line);}
  .donut .num{position:relative;font-family:var(--mono);font-weight:700;font-size:22px;z-index:1;font-variant-numeric:tabular-nums;}
  .donut-txt .big{font-size:13px;font-weight:600;}
  .donut-txt .small{font-size:12px;color:var(--ink-2);margin-top:2px;}
  .checks{display:flex;flex-direction:column;gap:10px;margin-top:auto;}
  .check{display:flex;align-items:center;gap:10px;font-size:13px;padding:9px 12px;border-radius:10px;background:var(--surface-2);border:1px solid var(--line);}
  .check .mk{width:20px;height:20px;border-radius:50%;display:grid;place-items:center;flex:none;font-size:12px;font-weight:700;color:#fff;}
  .check.ok .mk{background:var(--good);}.check.bad .mk{background:var(--crit);}
  .check .k{color:var(--ink-2);}
  .check .v{margin-left:auto;font-family:var(--mono);font-weight:600;font-variant-numeric:tabular-nums;}
  .finding{margin-top:20px;background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:14px;padding:20px 22px;box-shadow:var(--shadow);}
  .finding.crit{border-left-color:var(--crit);}
  .finding h3{margin:0 0 6px;font-size:15px;display:flex;align-items:center;gap:9px;}
  .finding p{margin:0;color:var(--ink-2);font-size:13.5px;max-width:76ch;}
  .finding code{font-family:var(--mono);background:var(--surface-2);border:1px solid var(--line);border-radius:5px;padding:1px 5px;font-size:12px;color:var(--ink);unicode-bidi:plaintext;}
  .finding .exlist{margin:12px 0 0;padding:0;list-style:none;display:flex;flex-direction:column;gap:5px;}
  .finding .exlist li{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);unicode-bidi:plaintext;word-break:break-all;display:flex;gap:8px;}
  .finding .exlist .d{color:var(--warn);font-weight:600;flex:none;}
  .tables{margin-top:20px;}
  .seg{display:inline-flex;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:4px;gap:3px;margin-bottom:16px;}
  .seg button{font-family:var(--sans);font-size:13px;font-weight:600;color:var(--ink-2);background:none;border:0;padding:7px 14px;border-radius:7px;cursor:pointer;transition:all .15s;}
  .seg button[aria-selected="true"]{background:var(--surface);color:var(--accent);box-shadow:var(--shadow);}
  .seg button:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
  .tbl-scroll{overflow-x:auto;border:1px solid var(--line);border-radius:14px;}
  table{width:100%;border-collapse:collapse;font-size:13px;min-width:520px;}
  thead th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3);font-weight:600;padding:12px 16px;background:var(--surface-2);border-bottom:1px solid var(--line);}
  thead th.num{text-align:right;}
  tbody td{padding:11px 16px;border-bottom:1px solid var(--line);vertical-align:middle;}
  tbody tr:last-child td{border-bottom:0;}
  tbody tr:hover td{background:var(--surface-2);}
  .rank{font-family:var(--mono);color:var(--ink-3);font-variant-numeric:tabular-nums;width:34px;}
  .url{font-family:var(--mono);font-size:12px;color:var(--ink);unicode-bidi:plaintext;word-break:break-all;}
  .url .host{color:var(--ink-3);}
  td.metric{text-align:right;white-space:nowrap;width:150px;}
  .metric .mbar{display:inline-block;height:6px;border-radius:3px;background:var(--accent);vertical-align:middle;margin-right:8px;opacity:.55;}
  .metric .mval{font-family:var(--mono);font-weight:600;font-variant-numeric:tabular-nums;}
  .tie-note{font-size:11.5px;color:var(--ink-3);margin:10px 2px 0;}
  .section-title{font-size:15px;margin:34px 0 4px;letter-spacing:-.01em;}
  .empty{color:var(--ink-3);font-size:13px;padding:20px;text-align:center;background:var(--surface-2);border:1px dashed var(--line-strong);border-radius:12px;}
  footer{margin-top:40px;padding-top:20px;border-top:1px solid var(--line);font-size:12px;color:var(--ink-3);display:flex;flex-wrap:wrap;align-items:center;gap:6px 18px;}
  footer code{font-family:var(--mono);}
  footer .repo{margin-left:auto;display:inline-flex;align-items:center;gap:7px;color:var(--ink-2);text-decoration:none;font-weight:600;padding:6px 12px;border:1px solid var(--line);border-radius:8px;transition:all .15s;}
  footer .repo:hover{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 45%,var(--line));background:var(--surface);}
  footer .repo:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
  footer .repo svg{width:15px;height:15px;fill:currentColor;flex:none;}
  @media (max-width:860px){.kpis{grid-template-columns:repeat(2,1fr);}.grid-2{grid-template-columns:1fr;}}
  @media (prefers-reduced-motion:reduce){.bar-fill{transition:none;}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <div class="eyebrow">Internal Linking Analysis &middot; Chapter 10</div>
      <h1>Link graph health for <span class="dom" id="domain"></span></h1>
      <p class="sub" id="subline"></p>
    </div>
    <div class="verdict good" id="verdict"><span class="dot"></span> <span id="verdictText"></span></div>
  </header>
  <section class="kpis" id="kpis"></section>
  <section class="grid-2">
    <div class="card">
      <h2>Click-depth distribution</h2>
      <p class="hint">How many clicks from the homepage each page sits. Shallower is stronger &mdash; crawlers and equity both fade with depth.</p>
      <div id="depthBody"></div>
    </div>
    <div class="card">
      <h2>Reachability</h2>
      <p class="hint">Every page should be reachable from the homepage, with none orphaned.</p>
      <div class="reach" id="reachBody"></div>
    </div>
  </section>
  <div id="findings"></div>
  <section class="tables" id="tablesSection"></section>
  <footer id="footer"></footer>
</div>
<script>
const DATA = __REPORT_DATA__;
const nf = new Intl.NumberFormat("en-US");
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

const HOST = (DATA.homepage || "").replace(/\/+$/, "");
$("domain").textContent = (HOST || "this site").replace(/^https?:\/\//, "");
const homePresent = DATA.homepage_present_in_graph;
$("subline").textContent =
  nf.format(DATA.total_pages_in_graph || 0) + " pages · " +
  nf.format(DATA.total_internal_links || 0) + " internal links" +
  (DATA.top_pages_by_pagerank ? " · PageRank computed" : "");

function shortUrl(u) {
  let path = HOST && u.startsWith(HOST) ? u.slice(HOST.length) : u;
  try { path = decodeURI(path); } catch (e) {}
  if (path === "" || path === "/") return '<span class="host">' + esc(HOST) + '</span>/';
  return '<span class="host">…</span>' + esc(path);
}

/* ---- findings (data-driven) ---- */
const findings = [];
const il = DATA.top_pages_by_inlinks || [];
if (il.length > 1 && il.every(r => r.inlinks === il[0].inlinks)) {
  findings.push({ sev: "warn", title: "Link equity is undifferentiated",
    body: "The top " + il.length + " URLs are <b>all tied at " + nf.format(il[0].inlinks) +
      " inbound links</b> — typically the signature of a site-wide menu that links every section from every page. Nothing signals which pages matter most. Consider trimming the global menu and adding contextual links from strong pages to your priority targets." });
}
const deep = DATA.pages_deeper_than_threshold;
if (deep && deep.count > 0) {
  findings.push({ sev: "crit", title: deep.count + " page" + (deep.count === 1 ? "" : "s") + " sit beyond depth " + deep.threshold,
    body: "The deepest page is <b>" + (DATA.max_click_depth) + " clicks</b> from the homepage. Pages this deep are crawled less often and receive less internal equity. Flatten navigation or add shortcut links to pull them closer to home.",
    examples: (deep.examples || []).slice(0, 8) });
}
if ((DATA.orphans_zero_inbound_count || 0) > 0) {
  findings.push({ sev: "crit", title: nf.format(DATA.orphans_zero_inbound_count) + " orphan page" + (DATA.orphans_zero_inbound_count === 1 ? "" : "s"),
    body: "These pages have <b>zero inbound internal links</b>, so crawlers can only reach them via the sitemap or external links. Add links to them from relevant hubs.",
    examples: (DATA.orphans_zero_inbound || []).slice(0, 8).map(u => ({ url: u })) });
}
const sd = DATA.sitemap_diff;
if (sd && sd.in_sitemap_only_count > 0) {
  findings.push({ sev: "warn", title: nf.format(sd.in_sitemap_only_count) + " sitemap-only page" + (sd.in_sitemap_only_count === 1 ? "" : "s"),
    body: "These URLs appear in the sitemap but have <b>no inbound internal links</b> in the crawl — a common indexing gap. Link to them internally so they earn crawl priority and equity.",
    examples: (sd.in_sitemap_only || []).slice(0, 8).map(u => ({ url: u })) });
}
if (!homePresent) {
  findings.unshift({ sev: "crit", title: "Homepage not found in the crawl graph",
    body: "Depth metrics were skipped because the supplied homepage URL isn't a node in the graph. Re-run with the exact homepage URL as it appears in the crawl (watch the trailing slash)." });
}

/* ---- verdict ---- */
let v = { cls: "good", text: "Structurally healthy" };
if (!homePresent) v = { cls: "crit", text: "Homepage missing from graph" };
else if ((DATA.orphans_zero_inbound_count || 0) > 0 || (DATA.unreachable_from_homepage_count || 0) > 0)
  v = { cls: "crit", text: "Orphans detected" };
else if (findings.length) v = { cls: "warn", text: "Healthy reach, issues to review" };
$("verdict").className = "verdict " + v.cls;
$("verdictText").textContent = v.text;

/* ---- KPIs ---- */
const dash = "—";
const kpis = [
  { label: "Pages crawled", val: nf.format(DATA.total_pages_in_graph || 0), foot: "nodes in the link graph" },
  { label: "Internal links", val: nf.format(DATA.total_internal_links || 0), foot: "edges in the graph" },
  { label: "Avg click depth", val: homePresent ? (DATA.avg_click_depth ?? dash) : dash, foot: "clicks from homepage",
    state: homePresent && DATA.avg_click_depth <= 3 ? "good" : (homePresent ? "warn" : "") },
  { label: "Max click depth", val: homePresent ? (DATA.max_click_depth ?? dash) : dash, foot: "deepest page",
    state: homePresent && (DATA.max_click_depth || 0) > (DATA.pages_deeper_than_threshold?.threshold ?? 3) ? "warn" : "good" },
  { label: "Orphan pages", val: nf.format(DATA.orphans_zero_inbound_count || 0), foot: "zero inbound links",
    state: (DATA.orphans_zero_inbound_count || 0) > 0 ? "crit" : "good" },
  { label: "Within depth 3", val: homePresent ? (DATA.percent_at_or_below_depth_3 ?? dash) : dash, unit: homePresent ? "%" : "", foot: "of all pages",
    state: homePresent ? ((DATA.percent_at_or_below_depth_3 || 0) >= 80 ? "good" : "warn") : "" },
];
$("kpis").innerHTML = kpis.map(k => '<div class="kpi ' + (k.state ? "state-" + k.state : "") + '">' +
  '<div class="label">' + k.label + '</div>' +
  '<div class="val">' + k.val + (k.unit ? '<span class="unit">' + k.unit + '</span>' : "") + '</div>' +
  '<div class="foot">' + k.foot + '</div></div>').join("");

/* ---- depth ladder ---- */
const dist = DATA.depth_distribution;
if (homePresent && dist && Object.keys(dist).length) {
  const entries = Object.entries(dist);
  const max = Math.max(...entries.map(([, v]) => v));
  const thr = DATA.pages_deeper_than_threshold?.threshold ?? 3;
  const rows = entries.map(([k, val]) => {
    const numeric = k === "5+" ? 5 : parseInt(k, 10);
    const beyond = !isNaN(numeric) && numeric > thr;
    const isHome = /homepage/.test(k);
    const tier = isHome ? "<b>0</b> · home" : (k === "5+" ? "<b>5+</b> clicks" : "<b>" + k + "</b> click" + (k === "1" ? "" : "s"));
    return '<div class="rung ' + (beyond ? "beyond" : "") + '">' +
      '<div class="tier">' + tier + '</div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:0" data-w="' + (val / max * 100).toFixed(1) + '"></div></div>' +
      '<div class="count">' + nf.format(val) + '</div></div>';
  }).join("");
  const beyondCount = deep ? deep.count : 0;
  $("depthBody").innerHTML = '<div class="ladder">' + rows + '</div>' +
    '<div class="threshold-note"><span class="swatch" style="background:var(--warn)"></span>' +
    'Beyond depth ' + thr + ' (the chapter’s warning threshold) — <b style="color:var(--ink);margin:0 3px">' +
    nf.format(beyondCount) + '</b> pages</div>';
  requestAnimationFrame(() => document.querySelectorAll(".bar-fill").forEach(b => b.style.width = b.dataset.w + "%"));
} else {
  $("depthBody").innerHTML = '<div class="empty">Depth metrics unavailable — homepage not present in the crawl graph.</div>';
}

/* ---- reachability ---- */
const total = DATA.total_pages_in_graph || 0;
const pct = homePresent ? (DATA.percent_at_or_below_depth_3 ?? 0) : 0;
const within3 = Math.round(total * pct / 100);
const orphans = DATA.orphans_zero_inbound_count || 0;
const unreach = DATA.unreachable_from_homepage_count || 0;
$("reachBody").innerHTML =
  (homePresent
    ? '<div class="donut-wrap"><div class="donut" style="--pct:' + pct + '"><span class="num">' +
        Math.round(pct) + '<span style="font-size:13px">%</span></span></div>' +
        '<div class="donut-txt"><div class="big">within depth 3</div>' +
        '<div class="small">' + nf.format(within3) + ' of ' + nf.format(total) + ' pages sit ≤ 3 clicks from home.</div></div></div>'
    : '') +
  '<div class="checks">' +
    check(orphans === 0, "Orphan pages (no inlinks)", nf.format(orphans)) +
    check(unreach === 0, "Unreachable from home", nf.format(unreach)) +
    check(homePresent, "Homepage in graph", homePresent ? "yes" : "no") +
  '</div>';
function check(ok, k, val) {
  return '<div class="check ' + (ok ? "ok" : "bad") + '"><span class="mk">' + (ok ? "✓" : "!") + '</span>' +
    '<span class="k">' + k + '</span><span class="v">' + val + '</span></div>';
}

/* ---- findings render ---- */
$("findings").innerHTML = findings.length ? findings.map(f => {
  const ex = f.examples && f.examples.length
    ? '<ul class="exlist">' + f.examples.map(e =>
        '<li>' + (e.depth != null ? '<span class="d">d' + e.depth + '</span>' : "") +
        '<span>' + shortUrl(e.url) + '</span></li>').join("") + '</ul>'
    : "";
  return '<div class="finding ' + (f.sev === "crit" ? "crit" : "") + '">' +
    '<h3><span class="pill ' + f.sev + '">Finding</span> ' + esc(f.title) + '</h3>' +
    '<p>' + f.body + '</p>' + ex + '</div>';
}).join("") :
  '<div class="finding" style="border-left-color:var(--good)"><h3><span class="pill good">All clear</span> No structural issues detected</h3>' +
  '<p>No orphans, no unreachable pages, and nothing beyond the depth threshold. Internal linking looks healthy.</p></div>';

/* ---- top-pages tables ---- */
const metrics = [
  { key: "pagerank", head: "PageRank", list: "top_pages_by_pagerank", label: "By PageRank", fmt: v => v.toFixed(6),
    tie: "All listed pages share the same PageRank — equity is evenly diffused rather than concentrated." },
  { key: "inlinks", head: "Inlinks", list: "top_pages_by_inlinks", label: "By inlinks", fmt: v => nf.format(v),
    tie: "All listed pages are tied on inbound links — the fingerprint of a site-wide navigation menu." },
  { key: "outlinks", head: "Outlinks", list: "top_pages_by_outlinks", label: "By outlinks", fmt: v => nf.format(v),
    tie: "All listed pages emit the same number of links — typically templated archive/pagination pages." },
].filter(m => Array.isArray(DATA[m.list]) && DATA[m.list].length);

if (metrics.length) {
  $("tablesSection").innerHTML =
    '<h2 class="section-title">Top pages</h2>' +
    '<div class="seg" role="tablist" aria-label="Ranking metric">' +
      metrics.map((m, i) => '<button role="tab" aria-selected="' + (i === 0) + '" data-key="' + m.key + '">' + m.label + '</button>').join("") +
    '</div>' +
    '<div class="tbl-scroll"><table><thead><tr><th class="rank">#</th><th>URL</th>' +
      '<th class="num" id="metricHead"></th></tr></thead><tbody id="tbody"></tbody></table></div>' +
    '<p class="tie-note" id="tieNote"></p>';
  const byKey = Object.fromEntries(metrics.map(m => [m.key, m]));
  function render(key) {
    const m = byKey[key];
    const rows = DATA[m.list];
    const maxV = Math.max(...rows.map(r => r[m.key]));
    const allTied = rows.length > 1 && rows.every(r => r[m.key] === rows[0][m.key]);
    $("metricHead").textContent = m.head;
    $("tieNote").textContent = allTied ? m.tie : "";
    $("tbody").innerHTML = rows.map((r, i) => {
      const val = r[m.key];
      const w = Math.max(6, maxV ? val / maxV * 66 : 6);
      return '<tr><td class="rank">' + (i + 1) + '</td>' +
        '<td class="url">' + shortUrl(r.url) + '</td>' +
        '<td class="metric"><span class="mbar" style="width:' + w + 'px"></span>' +
        '<span class="mval">' + m.fmt(val) + '</span></td></tr>';
    }).join("");
  }
  const seg = $("tablesSection").querySelector(".seg");
  seg.addEventListener("click", e => {
    const btn = e.target.closest("button"); if (!btn) return;
    seg.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", b === btn));
    render(btn.dataset.key);
  });
  render(metrics[0].key);
}

/* ---- footer ---- */
const REPO_URL = "https://github.com/nimajafari/seo-for-engineers/tree/main/volume-1-code-and-craft/chapter-10-internal-linking";
const GH_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>';
const foot = ['Generated by <code>link-graph-analyzer.py</code>'];
if (DATA.homepage) foot.push('Homepage: <code>' + esc(DATA.homepage) + '</code>');
if (deep) foot.push('Depth warning threshold: ' + deep.threshold);
$("footer").innerHTML = foot.map(s => '<span>' + s + '</span>').join("") +
  '<a class="repo" href="' + REPO_URL + '" target="_blank" rel="noopener">' + GH_ICON + 'Chapter 10 on GitHub</a>';
</script>
</body>
</html>
"""


def render_html_report(report: dict[str, Any]) -> str:
    """Render the report dict into a self-contained HTML dashboard."""
    # Inject the report as JSON. Escape ``<`` so a stray "</script>" in any
    # URL can never break out of the script element.
    data_json = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    return HTML_TEMPLATE.replace("__REPORT_DATA__", data_json)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--crawl",
        required=True,
        help="Path to a crawl export CSV with 'source' and 'destination' columns.",
    )
    parser.add_argument(
        "--homepage",
        required=True,
        help="The site's homepage URL, used as the graph root for depth analysis.",
    )
    parser.add_argument(
        "--sitemap",
        default=None,
        help="Optional sitemap URL for the sitemap-vs-graph orphan diff.",
    )
    parser.add_argument(
        "--pagerank",
        action="store_true",
        help="Compute PageRank across the internal graph and include in the report.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="Number of top pages to include in by-inlinks, by-outlinks, by-PageRank rankings.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write the JSON report. Defaults to stdout.",
    )
    parser.add_argument(
        "--html",
        default=None,
        help="Optional path to write a self-contained HTML visualization "
        "of the report (opens in any browser, no dependencies).",
    )
    args = parser.parse_args()

    crawl_path = Path(args.crawl)
    if not crawl_path.exists():
        print(f"FATAL: crawl file not found, {crawl_path}", file=sys.stderr)
        return 2

    print(f"Building graph from {crawl_path}...", file=sys.stderr)
    g = build_graph(crawl_path)
    print(
        f"Graph built, {g.number_of_nodes()} nodes, {g.number_of_edges()} edges.",
        file=sys.stderr,
    )

    sitemap_urls: set[str] | None = None
    if args.sitemap:
        print(f"Fetching sitemap from {args.sitemap}...", file=sys.stderr)
        sitemap_urls = parse_sitemap(args.sitemap)
        print(f"Sitemap loaded, {len(sitemap_urls)} URLs.", file=sys.stderr)

    report = analyze(
        g,
        homepage=args.homepage,
        sitemap_urls=sitemap_urls,
        compute_pagerank=args.pagerank,
        top_n=args.top_n,
    )

    output_text = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)

    if args.html:
        Path(args.html).write_text(render_html_report(report), encoding="utf-8")
        print(f"Visualization written to {args.html}", file=sys.stderr)

    # Heuristic exit code, fail if any orphan-or-depth signal is severe.
    severe = False
    if report.get("orphans_zero_inbound_count", 0) > 0:
        severe = True
    if report.get("unreachable_from_homepage_count", 0) > 0:
        severe = True
    return 1 if severe else 0


if __name__ == "__main__":
    sys.exit(main())