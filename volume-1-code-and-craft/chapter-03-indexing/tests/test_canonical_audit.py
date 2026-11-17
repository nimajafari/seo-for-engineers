"""Tests for canonical-audit.py."""

from __future__ import annotations

import csv
import sys

import pytest

from conftest import Route, load_script

ca = load_script("canonical-audit.py", "canonical_audit")


def page(head: str = "", body: str = "<p>content</p>") -> str:
    return f"<!doctype html><html><head><title>t</title>{head}</head><body>{body}</body></html>"


def canon(href: str) -> str:
    return f'<link rel="canonical" href="{href}">'


# normalize_url ----------------------------------------------------------

@pytest.mark.parametrize(
    "a, b",
    [
        ("https://example.com", "https://example.com/"),
        ("https://example.com/a/", "https://example.com/a"),
        ("HTTPS://Example.COM/a", "https://example.com/a"),
        ("https://example.com:443/a", "https://example.com/a"),
        ("http://example.com:80/a", "http://example.com/a"),
        ("https://example.com/café", "https://example.com/caf%C3%A9"),
        ("https://example.com/caf%c3%a9", "https://example.com/caf%C3%A9"),
        ("https://bücher.de/", "https://xn--bcher-kva.de/"),
        ("https://example.com/a#frag", "https://example.com/a"),
    ],
)
def test_normalize_url_equates_equivalent_forms(a, b):
    assert ca.normalize_url(a) == ca.normalize_url(b)


@pytest.mark.parametrize(
    "a, b",
    [
        ("https://example.com:8443/", "https://example.com/"),
        ("http://example.com/", "https://example.com/"),
        ("https://example.com/A", "https://example.com/a"),  # path case matters
        ("https://example.com/a?x=1", "https://example.com/a"),
    ],
)
def test_normalize_url_keeps_distinct_urls_distinct(a, b):
    assert ca.normalize_url(a) != ca.normalize_url(b)


def test_strip_tracking_params_keeps_identity_params():
    assert ca.strip_tracking_params("https://e.com/p?id=7&utm_source=x&gclid=y") == (
        "https://e.com/p?id=7"
    )


def test_find_header_canonicals():
    header = '<https://e.com/a>; rel="canonical", <https://e.com/b.pdf>; rel="alternate"'
    assert ca.find_header_canonicals(header) == ["https://e.com/a"]
    assert ca.find_header_canonicals(None) == []


# audit_url end to end ---------------------------------------------------

def audit(serve, routes, path):
    origin = serve(routes)
    return ca.audit_url(origin + path)


def test_clean_self_canonical(serve):
    r = audit(serve, {"/a": Route(page(canon("{origin}/a")))}, "/a")
    assert r.is_clean, r.issues
    assert r.canonical_source == "html"


def test_root_canonical_without_trailing_slash_is_self(serve):
    # requests reports the page as origin + "/"; the canonical omits it.
    r = audit(serve, {"/": Route(page(canon("{origin}")))}, "/")
    assert r.is_clean, r.issues


def test_non_ascii_path_matches_percent_encoded_final_url(serve):
    # Body is UTF-8 with only a <meta charset>: the header has no charset,
    # the case requests would decode as ISO-8859-1.
    html = page('<meta charset="utf-8">' + canon("{origin}/café"))
    routes = {"/caf%C3%A9": Route(html, headers={"Content-Type": "text/html"})}
    r = audit(serve, routes, "/caf%C3%A9")
    assert r.is_clean, r.issues


def test_missing_canonical(serve):
    r = audit(serve, {"/a": Route(page())}, "/a")
    assert r.issues == ["missing canonical (no <link> in <head>, no Link header)"]


def test_canonical_after_head_breaking_element_is_outside_head(serve):
    # An <img> is not allowed in <head>; the HTML parser closes <head>
    # there, so the canonical after it is in <body> and ignored.
    html = "<html><head><title>t</title><img src=x.gif>" + canon("{origin}/a") + "</head><body></body></html>"
    r = audit(serve, {"/a": Route(html)}, "/a")
    assert any("outside <head>" in i for i in r.issues)
    assert any(i.startswith("missing canonical") for i in r.issues)


def test_link_header_canonical_counts(serve):
    routes = {"/doc.pdf": Route(
        b"%PDF-1.4",
        headers={"Content-Type": "application/pdf",
                 "Link": '<{origin}/doc.pdf>; rel="canonical"'},
    )}
    r = audit(serve, routes, "/doc.pdf")
    assert r.is_clean, r.issues
    assert r.canonical_source == "header"


def test_conflicting_html_and_header_canonicals(serve):
    routes = {"/a": Route(
        page(canon("{origin}/a")),
        headers={"Content-Type": "text/html", "Link": '<{origin}/b>; rel="canonical"'},
    )}
    r = audit(serve, routes, "/a")
    assert any(i.startswith("conflicting canonicals (2") for i in r.issues)


def test_duplicate_identical_canonicals(serve):
    r = audit(serve, {"/a": Route(page(canon("{origin}/a") + canon("{origin}/a/")))}, "/a")
    assert r.issues == ["multiple canonicals (2) with the same target"]


def test_relative_canonical_is_resolved_and_checked(serve):
    r = audit(serve, {"/a": Route(page(canon("/b")))}, "/a")
    assert r.canonical_resolved.endswith("/b")
    assert any("relative" in i for i in r.issues)
    # Previously the mismatch check was skipped for relative hrefs.
    assert "page URL does not match canonical (page may be a duplicate)" in r.issues


def test_relative_canonical_honors_base_href(serve):
    html = page('<base href="/sub/">' + canon("a"))
    r = audit(serve, {"/sub/a": Route(html)}, "/sub/a")
    assert r.canonical_resolved.endswith("/sub/a")
    assert not any("does not match" in i for i in r.issues)


def test_tracking_request_with_clean_canonical_is_ok(serve):
    r = audit(serve, {"/a?utm_source=mail": Route(page(canon("{origin}/a")))},
              "/a?utm_source=mail")
    assert r.is_clean, r.issues


def test_canonical_built_from_request_url_is_flagged(serve):
    routes = {"/a?gclid=1": Route(page(canon("{origin}/a?gclid=1")))}
    r = audit(serve, routes, "/a?gclid=1")
    assert "canonical contains tracking parameters: gclid" in r.issues


def test_cross_host_canonical(serve):
    r = audit(serve, {"/a": Route(page(canon("https://other.example/a")))}, "/a")
    assert "canonical points to a different host (other.example)" in r.issues


def test_non_http_canonical(serve):
    r = audit(serve, {"/a": Route(page(canon("javascript:void(0)")))}, "/a")
    assert any("not an http(s) URL" in i for i in r.issues)


def test_rel_matching_is_exact_and_case_insensitive(serve):
    html = page('<link rel="noncanonical" href="/x"><link rel="Canonical" href="{origin}/a">')
    r = audit(serve, {"/a": Route(html)}, "/a")
    assert r.canonical_count == 1
    assert r.is_clean, r.issues


def test_error_status(serve):
    r = audit(serve, {}, "/gone")
    assert r.issues == ["non-success status 404"]


def test_request_failure():
    r = ca.audit_url("http://127.0.0.1:9/")
    assert r.error and r.error.startswith("request failed")


# main -------------------------------------------------------------------

def test_main_batch_writes_csv_and_gates(serve, tmp_path, monkeypatch):
    origin = serve({"/ok": Route(page(canon("{origin}/ok"))), "/bad": Route(page())})
    urls = tmp_path / "urls.txt"
    urls.write_text(f"# comment\n{origin}/ok\n{origin}/bad\n")
    out = tmp_path / "r.csv"
    monkeypatch.setattr(sys, "argv", ["canonical-audit.py", "--urls", str(urls), "--csv", str(out)])
    assert ca.main() == 1
    rows = list(csv.DictReader(out.open()))
    assert [r["is_clean"] for r in rows] == ["yes", "no"]
    assert rows[0]["canonical_source"] == "html"


@pytest.mark.parametrize("content", [None, "# only a comment\n"])
def test_main_bad_urls_file_exits_two(tmp_path, monkeypatch, capsys, content):
    urls = tmp_path / "urls.txt"
    if content is not None:
        urls.write_text(content)
    monkeypatch.setattr(sys, "argv", ["canonical-audit.py", "--urls", str(urls), "--csv", "x.csv"])
    assert ca.main() == 2
    assert "urls" in capsys.readouterr().err.lower()
