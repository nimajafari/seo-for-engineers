"""Tests for link-graph-audit.py."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "link-graph-audit.py"
_spec = importlib.util.spec_from_file_location("link_graph_audit", SCRIPT)
lga = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = lga
_spec.loader.exec_module(lga)

H = "https://example.com/"

CRAWL = f"""source_url,target_url,target_status_code
{H},{H}about,200
{H},{H}old-page,301
{H},{H}products,200
{H}products,{H}products/widget,200
{H}products,{H}products,200
{H}products,{H}gone,404
{H}products,{H}timeout,0
{H}landing,{H},200
{H}about,,200
"""


@pytest.fixture
def crawl_file(tmp_path):
    path = tmp_path / "crawl.csv"
    path.write_text(CRAWL)
    return path


def run(tmp_path, crawl_file, *extra, homepage=H):
    out = tmp_path / "report.csv"
    argv = ["link-graph-audit.py", "--crawl", str(crawl_file),
            "--homepage", homepage, "--out", str(out), *extra]
    old = sys.argv
    sys.argv = argv
    try:
        code = lga.main()
    finally:
        sys.argv = old
    rows = {r["url"]: r for r in csv.DictReader(out.open())} if out.exists() else {}
    return code, rows


def test_load_crawl_drops_empty_urls_and_accepts_status_alias(tmp_path, capsys):
    path = tmp_path / "c.csv"
    path.write_text(f"source_url,target_url,status_code\n{H},{H}a,200\n{H},,200\n")
    df = lga.load_crawl(path)
    assert len(df) == 1
    assert "target_status_code" in df.columns
    assert "dropped 1 rows with an empty URL" in capsys.readouterr().err


def test_no_nan_node(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    assert "nan" not in rows and "<NA>" not in rows


def test_redirects_are_not_broken(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    assert rows[H]["broken_link_count"] == "0"
    assert rows[H]["redirect_link_count"] == "1"


def test_4xx_and_no_response_are_broken(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    assert rows[f"{H}products"]["broken_link_count"] == "2"  # 404 + status 0


def test_self_links_are_ignored(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    assert rows[f"{H}products"]["in_degree"] == "1"


def test_homepage_without_trailing_slash_still_gets_depths(tmp_path, crawl_file, capsys):
    _, rows = run(tmp_path, crawl_file, homepage="https://example.com")
    assert rows[H]["click_depth"] == "0"
    assert rows[f"{H}products/widget"]["click_depth"] == "2"
    assert "using homepage" in capsys.readouterr().err


def test_unreachable_pages_are_reported(tmp_path, crawl_file, capsys):
    _, rows = run(tmp_path, crawl_file)
    assert rows[f"{H}landing"]["click_depth"] == ""
    assert "1 URLs in the graph are unreachable" in capsys.readouterr().err


def test_in_graph_orphan(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    assert rows[f"{H}landing"]["is_orphan"] == "yes"
    assert rows[H]["is_orphan"] == "no"  # the homepage is never an orphan


def test_known_urls_find_pages_the_crawl_never_reached(tmp_path, crawl_file):
    known = tmp_path / "known.txt"
    known.write_text(f"# sitemap\n{H}\n{H}about\n{H}forgotten\n")
    code, rows = run(tmp_path, crawl_file, "--known-urls", str(known))
    assert code == 0
    forgotten = rows[f"{H}forgotten"]
    assert forgotten["is_orphan"] == "yes"
    assert forgotten["pagerank"] == "" and forgotten["in_degree"] == "0"
    assert rows[f"{H}about"]["is_orphan"] == "no"


def test_unreadable_known_urls_exits_two(tmp_path, crawl_file):
    code, _ = run(tmp_path, crawl_file, "--known-urls", str(tmp_path / "nope.txt"))
    assert code == 2


def test_report_sorted_by_pagerank(tmp_path, crawl_file):
    _, rows = run(tmp_path, crawl_file)
    ranks = [float(r["pagerank"]) for r in rows.values() if r["pagerank"]]
    assert ranks == sorted(ranks, reverse=True)
    assert sum(ranks) == pytest.approx(1.0, abs=1e-4)


def test_missing_columns_fail(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text("source_url,target_url\nhttps://a/,https://b/\n")
    code, _ = run(tmp_path, path)
    assert code == 1


def test_empty_graph_fails(tmp_path):
    path = tmp_path / "c.csv"
    path.write_text(f"source_url,target_url,target_status_code\n{H},{H}x,404\n")
    code, _ = run(tmp_path, path)
    assert code == 1
