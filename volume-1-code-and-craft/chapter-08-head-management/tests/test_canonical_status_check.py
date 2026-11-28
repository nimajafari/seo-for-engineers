"""Tests for canonical-status-check.sh, run with bash against a local
HTTP server. Needs bash, curl, and perl, as the script does."""

from __future__ import annotations

import shutil
import subprocess

import pytest
from conftest import CHAPTER

SCRIPT = CHAPTER / "canonical-status-check.sh"

pytestmark = pytest.mark.skipif(
    not all(shutil.which(tool) for tool in ("bash", "curl", "perl")),
    reason="needs bash, curl, and perl",
)


def head(canonical_tag: str) -> str:
    return f"<!doctype html><html><head><title>t</title>{canonical_tag}</head><body></body></html>"


def run(tmp_path, *urls: str, raw: str | None = None):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(raw if raw is not None else "\n".join(urls) + "\n")
    proc = subprocess.run(
        ["bash", str(SCRIPT), str(urls_file)], capture_output=True, text=True, timeout=60, check=False
    )
    return proc.returncode, proc.stdout


def test_good_canonical_passes(site, tmp_path):
    url = site.add("/p", head(f'<link rel="canonical" href="{site.url("/p")}">'))
    code, out = run(tmp_path, url)
    assert code == 0 and "All 1 canonical URLs return 200." in out


@pytest.mark.parametrize("tag", [
    "<link href='{u}' rel='canonical'>",
    '<link\n  rel="canonical"\n  href="{u}" />',
    "<link rel=canonical href={u}>",
    '<LINK REL="Canonical" HREF="{u}">',
])
def test_attribute_order_quotes_and_case(site, tmp_path, tag):
    url = site.add("/p", head(tag.format(u=site.url("/p"))))
    assert run(tmp_path, url)[0] == 0


def test_canonical_that_redirects_fails(site, tmp_path):
    site.add("/good", head(""))
    site.redirect("/moved", "/good")
    url = site.add("/p", head(f'<link rel="canonical" href="{site.url("/moved")}">'))
    code, out = run(tmp_path, url)
    assert code == 1 and "redirects (HTTP 301" in out


def test_unreachable_canonical_reports_cleanly(site, tmp_path):
    url = site.add("/p", head('<link rel="canonical" href="http://127.0.0.1:1/x">'))
    code, out = run(tmp_path, url)
    assert code == 1 and "is unreachable" in out and "000000" not in out


def test_relative_canonical_fails(site, tmp_path):
    url = site.add("/p", head('<link rel="canonical" href="/p">'))
    code, out = run(tmp_path, url)
    assert code == 1 and "is not an absolute URL" in out


def test_error_page_is_reported_as_such(site, tmp_path):
    code, out = run(tmp_path, site.url("/missing"))
    assert code == 1 and "returned HTTP 404" in out


def test_duplicate_canonicals_fail_but_body_and_comments_do_not_count(site, tmp_path):
    u = site.url("/p")
    dup = site.add("/dup", head(f'<link rel="canonical" href="{u}"><link rel="canonical" href="{u}">'))
    assert "2 canonical tags" in run(tmp_path, dup)[1]

    html = (f'<html><head><!-- <link rel="canonical" href="{u}x"> -->'
            f'<link rel="canonical" href="{u}"></head>'
            f'<body><link rel="canonical" href="{u}y"></body></html>')
    site.add("/p", html)
    assert run(tmp_path, u)[0] == 0


def test_crlf_and_comment_lines(site, tmp_path):
    url = site.add("/p", head(f'<link rel="canonical" href="{site.url("/p")}">'))
    assert run(tmp_path, raw=f"# staging\r\n\r\n{url}\r\n")[0] == 0


@pytest.mark.parametrize("raw", [None, "# only a comment\n"])
def test_usage_errors_exit_two(tmp_path, raw):
    if raw is None:
        proc = subprocess.run(["bash", str(SCRIPT), str(tmp_path / "missing.txt")],
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 2
    else:
        assert run(tmp_path, raw=raw)[0] == 2
