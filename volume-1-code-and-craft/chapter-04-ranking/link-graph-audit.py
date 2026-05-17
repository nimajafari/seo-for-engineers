#!/usr/bin/env python3
"""
link-graph-audit.py

Audit the internal link graph of a site. Compute PageRank, find orphans,
calculate click depth from the homepage, and count broken internal
links per source page.

Input is a crawl-export CSV with columns:
    source_url, target_url, target_status_code

Output is a per-URL CSV with columns:
    url, pagerank, in_degree, out_degree, click_depth, is_orphan,
    broken_link_count

Usage:
    python link-graph-audit.py \\
        --crawl crawl.csv \\
        --homepage https://example.com/ \\
        --out report.csv

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 4.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import networkx as nx
import pandas as pd

PAGERANK_DAMPING = 0.85
PAGERANK_MAX_ITER = 200
PAGERANK_TOLERANCE = 1e-6


def load_crawl(path: Path) -> pd.DataFrame:
    """Load a crawl-export CSV and validate the columns.

    Accepts ``target_status_code`` (the canonical form used in this
    script) or ``status_code`` as an alias for the response-code
    column. The latter matches the column name used in the Chapter 4
    inline snippet. Both are normalized to ``target_status_code``
    so the rest of the pipeline can assume the canonical name.
    """
    df = pd.read_csv(path)
    required_urls = {"source_url", "target_url"}
    missing_urls = required_urls - set(df.columns)
    if missing_urls:
        raise ValueError(
            f"crawl CSV is missing required columns: {sorted(missing_urls)}"
        )
    if "target_status_code" not in df.columns:
        if "status_code" in df.columns:
            df = df.rename(columns={"status_code": "target_status_code"})
        else:
            raise ValueError(
                "crawl CSV must have a 'target_status_code' or "
                "'status_code' column"
            )
    # Coerce status code to integer, dropping rows with non-numeric values.
    df["target_status_code"] = pd.to_numeric(
        df["target_status_code"], errors="coerce"
    )
    before = len(df)
    df = df.dropna(subset=["target_status_code"])
    df["target_status_code"] = df["target_status_code"].astype(int)
    dropped = before - len(df)
    if dropped:
        print(
            f"warning: dropped {dropped} rows with non-numeric status codes",
            file=sys.stderr,
        )
    return df


def build_graph(crawl: pd.DataFrame) -> nx.DiGraph:
    """Build a directed graph from 200-status edges only."""
    graph = nx.DiGraph()
    good = crawl[crawl["target_status_code"] == 200]
    for source, target in zip(good["source_url"], good["target_url"]):
        graph.add_edge(source, target)
    return graph


def compute_pagerank(graph: nx.DiGraph) -> dict[str, float]:
    """Compute PageRank with the canonical 0.85 damping factor."""
    if graph.number_of_nodes() == 0:
        return {}
    return nx.pagerank(
        graph,
        alpha=PAGERANK_DAMPING,
        max_iter=PAGERANK_MAX_ITER,
        tol=PAGERANK_TOLERANCE,
    )


def compute_depths(graph: nx.DiGraph, homepage: str) -> dict[str, int]:
    """Compute shortest-path click depth from the homepage."""
    if homepage not in graph:
        print(
            f"warning: homepage {homepage!r} not found in the link graph. "
            "Click depth will be unavailable.",
            file=sys.stderr,
        )
        return {}
    return nx.single_source_shortest_path_length(graph, homepage)


def count_broken_links(crawl: pd.DataFrame) -> dict[str, int]:
    """Count broken outbound internal links per source URL."""
    broken = crawl[crawl["target_status_code"] != 200]
    if broken.empty:
        return {}
    return broken.groupby("source_url").size().to_dict()


def find_orphans(graph: nx.DiGraph, homepage: str) -> set[str]:
    """Find nodes with in-degree zero, excluding the homepage."""
    return {
        node
        for node in graph.nodes()
        if graph.in_degree(node) == 0 and node != homepage
    }


def write_report(
    path: Path,
    graph: nx.DiGraph,
    pagerank: dict[str, float],
    depths: dict[str, int],
    orphans: set[str],
    broken_link_counts: dict[str, int],
) -> None:
    """Write the per-URL report CSV."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "url",
                "pagerank",
                "in_degree",
                "out_degree",
                "click_depth",
                "is_orphan",
                "broken_link_count",
            ]
        )
        # Sort by descending PageRank so the most important URLs are at the
        # top of the report.
        nodes_by_pagerank = sorted(
            graph.nodes(),
            key=lambda n: pagerank.get(n, 0.0),
            reverse=True,
        )
        for url in nodes_by_pagerank:
            writer.writerow(
                [
                    url,
                    f"{pagerank.get(url, 0.0):.6f}",
                    graph.in_degree(url),
                    graph.out_degree(url),
                    depths.get(url, ""),
                    "yes" if url in orphans else "no",
                    broken_link_counts.get(url, 0),
                ]
            )


def print_summary(
    graph: nx.DiGraph,
    depths: dict[str, int],
    orphans: set[str],
    broken_link_counts: dict[str, int],
) -> None:
    """Print a short summary of the audit."""
    total_urls = graph.number_of_nodes()
    total_edges = graph.number_of_edges()
    total_broken = sum(broken_link_counts.values())

    print(f"URLs in graph (200-status):     {total_urls}", file=sys.stderr)
    print(f"Internal links (200-status):    {total_edges}", file=sys.stderr)
    print(f"Orphans (in-degree 0):          {len(orphans)}", file=sys.stderr)
    print(
        f"Broken internal links:          {total_broken}",
        file=sys.stderr,
    )

    if depths:
        depth_buckets: dict[int, int] = {}
        for d in depths.values():
            bucket = min(d, 5)  # Bucket 5 covers depth 5+
            depth_buckets[bucket] = depth_buckets.get(bucket, 0) + 1
        print("Click-depth distribution:", file=sys.stderr)
        for d in sorted(depth_buckets):
            label = f"{d}+ " if d == 5 else f"{d}  "
            print(
                f"  depth {label}: {depth_buckets[d]} URLs",
                file=sys.stderr,
            )
        deep = sum(c for d, c in depth_buckets.items() if d >= 4)
        if deep:
            print(
                f"warning: {deep} URLs are 4+ clicks from the homepage. "
                "Consider editorial cross-links to surface them.",
                file=sys.stderr,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--crawl",
        required=True,
        help="Path to the crawl-export CSV.",
    )
    parser.add_argument(
        "--homepage",
        required=True,
        help="Canonical homepage URL, used as the source for click-depth "
        "calculation.",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to write the per-URL report CSV.",
    )
    args = parser.parse_args()

    try:
        crawl = load_crawl(Path(args.crawl))
    except Exception as exc:
        print(f"error loading crawl: {exc}", file=sys.stderr)
        return 1

    graph = build_graph(crawl)
    if graph.number_of_nodes() == 0:
        print("error: graph contains no 200-status nodes", file=sys.stderr)
        return 1

    pagerank = compute_pagerank(graph)
    depths = compute_depths(graph, args.homepage)
    orphans = find_orphans(graph, args.homepage)
    broken_link_counts = count_broken_links(crawl)

    write_report(
        Path(args.out),
        graph=graph,
        pagerank=pagerank,
        depths=depths,
        orphans=orphans,
        broken_link_counts=broken_link_counts,
    )
    print_summary(
        graph=graph,
        depths=depths,
        orphans=orphans,
        broken_link_counts=broken_link_counts,
    )
    print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())