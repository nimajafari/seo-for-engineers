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
        root = etree.fromstring(response.content)
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


def analyze(
    g: nx.DiGraph,
    homepage: str,
    sitemap_urls: set[str] | None = None,
    compute_pagerank: bool = False,
    top_n: int = 20,
) -> dict[str, Any]:
    """Run the full Chapter 10 analysis suite."""
    report: dict[str, Any] = {
        "homepage": homepage,
        "total_pages_in_graph": g.number_of_nodes(),
        "total_internal_links": g.number_of_edges(),
        "homepage_present_in_graph": homepage in g,
    }

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

    # Heuristic exit code, fail if any orphan-or-depth signal is severe.
    severe = False
    if report.get("orphans_zero_inbound_count", 0) > 0:
        severe = True
    if report.get("unreachable_from_homepage_count", 0) > 0:
        severe = True
    return 1 if severe else 0


if __name__ == "__main__":
    sys.exit(main())