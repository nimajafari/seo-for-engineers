"""Tests for rendering-debt-audit.py.

The script is loaded via importlib because its filename uses hyphens.
Unit tests run offline. The end-to-end tests serve pages from a local
HTTP server and render them in Chromium; they are skipped when the
Playwright browser is not installed (`playwright install chromium`).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import http.server
import importlib.util
import sys
import threading
from collections import Counter
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "rendering-debt-audit.py"
_spec = importlib.util.spec_from_file_location("rendering_debt_audit", SCRIPT_PATH)
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod  # dataclasses resolve annotations via sys.modules
_spec.loader.exec_module(mod)


# header_charset / extract_raw_text --------------------------------------

@pytest.mark.parametrize(
    "header, expected",
    [
        ("text/html; charset=utf-8", "utf-8"),
        ('text/html; charset="windows-1252"', "windows-1252"),
        ("text/html;charset=ISO-8859-1", "ISO-8859-1"),
        ("text/html", None),
        (None, None),
    ],
)
def test_header_charset(header, expected):
    assert mod.header_charset(header) == expected


UTF8_PAGE = (
    '<html><head><meta charset="utf-8"><title>Title words</title></head>'
    "<body><p>Zürich café 東京</p></body></html>"
).encode("utf-8")


def test_extract_raw_text_honors_meta_charset_without_header_charset():
    # requests would decode this as ISO-8859-1 (ZÃ¼rich); bytes + meta
    # charset must give the real text.
    assert mod.extract_raw_text(UTF8_PAGE, "text/html") == "Zürich café 東京"


def test_extract_raw_text_header_charset_wins():
    page = "<html><body><p>café</p></body></html>".encode("windows-1252")
    assert mod.extract_raw_text(page, "text/html; charset=windows-1252") == "café"


def test_extract_raw_text_reads_body_only():
    # <title> is not part of document.body.innerText on the rendered side.
    assert "Title" not in mod.extract_raw_text(UTF8_PAGE, "text/html")


def test_extract_raw_text_drops_non_rendered_elements():
    page = (
        b"<html><body><p>kept</p><script>var hidden=1</script>"
        b"<style>.x{}</style><noscript>enable js</noscript>"
        b"<template><p>inert</p></template></body></html>"
    )
    assert mod.extract_raw_text(page, "text/html") == "kept"


def test_extract_raw_text_without_body_tag():
    assert mod.extract_raw_text(b"<p>fragment only</p>", None) == "fragment only"


# tokenize / compute_score -----------------------------------------------

def test_tokenize_case_folds_and_counts():
    assert mod.tokenize("The the THE cat") == Counter({"the": 3, "cat": 1})


def test_tokenize_splits_unspaced_scripts_per_character():
    tokens = mod.tokenize("该域名 東京タワー hello")
    assert tokens["该"] == 1 and tokens["京"] == 1 and tokens["タ"] == 1
    assert tokens["hello"] == 1
    assert sum(tokens.values()) == 9


def test_tokenize_keeps_spaced_non_latin_words_whole():
    assert mod.tokenize("Данный домен") == Counter({"данный": 1, "домен": 1})


def test_compute_score_zero_when_rendered_matches_raw():
    tokens = Counter({"a": 2, "b": 1})
    assert mod.compute_score(tokens, tokens) == 0.0


def test_compute_score_counts_multiplicity():
    raw = Counter({"a": 1})
    rendered = Counter({"a": 3, "b": 1})
    # 2 extra "a" + 1 "b" out of 4 rendered tokens.
    assert mod.compute_score(raw, rendered) == pytest.approx(0.75)


def test_compute_score_empty_render_is_zero():
    assert mod.compute_score(Counter({"a": 1}), Counter()) == 0.0


def test_partial_cjk_injection_scores_only_new_characters():
    raw = mod.tokenize("東京タワー")
    rendered = mod.tokenize("東京タワーです")
    assert mod.compute_score(raw, rendered) == pytest.approx(2 / 7)


# error_summary ----------------------------------------------------------

def test_error_summary_keeps_first_line():
    exc = RuntimeError("Page.goto: net::ERR_NAME_NOT_RESOLVED\nCall log:\n  - navigating")
    assert mod.error_summary(exc) == "Page.goto: net::ERR_NAME_NOT_RESOLVED"


def test_error_summary_skips_leading_blank_lines_and_falls_back_to_type():
    assert mod.error_summary(ValueError("\n\n  real cause\nmore")) == "real cause"
    assert mod.error_summary(TimeoutError()) == "TimeoutError"


# load_urls / main_async / write_csv -------------------------------------

def test_load_urls_skips_blanks_and_comments(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# header\n\nhttps://a.example/\n  https://b.example/  \n")
    assert mod.load_urls(f) == ["https://a.example/", "https://b.example/"]


def _args(**kw):
    base = {"url": None, "urls": None, "csv": None}
    base.update(kw)
    return argparse.Namespace(**base)


def test_main_async_missing_urls_file_exits_two(tmp_path, capsys):
    rc = asyncio.run(mod.main_async(_args(urls=str(tmp_path / "nope.txt"), csv="x.csv")))
    assert rc == 2
    assert "Could not read --urls file" in capsys.readouterr().err


def test_main_async_empty_urls_file_exits_two(tmp_path, capsys):
    f = tmp_path / "urls.txt"
    f.write_text("# nothing here\n")
    rc = asyncio.run(mod.main_async(_args(urls=str(f), csv="x.csv")))
    assert rc == 2
    assert "No URLs found" in capsys.readouterr().err


def test_write_csv_round_trips(tmp_path):
    results = [
        mod.AuditResult("https://a.example/", 10, 20, 0.5),
        mod.AuditResult("https://b.example/", 0, 0, 0.0, error="403 Forbidden"),
    ]
    out = tmp_path / "r.csv"
    mod.write_csv(results, out)
    rows = list(csv.DictReader(out.open()))
    assert rows[0]["rendering_debt_pct"] == "50%"
    assert rows[1]["error"] == "403 Forbidden"
    assert len(out.read_text().splitlines()) == 3  # header + one line per URL


def test_main_requires_csv_for_batch(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["rendering-debt-audit.py", "--urls", "u.txt"])
    assert mod.main() == 2


# End-to-end with a real browser -----------------------------------------

PAGES = {
    "/static": (
        200,
        "<html><body><h1>Server rendered</h1><p>All words ship in HTML</p></body></html>",
    ),
    "/injected": (
        200,
        "<html><body><div id=app>Loading</div><script>"
        "document.getElementById('app').textContent = "
        "'one two three four five six seven eight nine';"
        "</script></body></html>",
    ),
    "/missing": (404, "<html><body>Not found</body></html>"),
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        status, body = PAGES.get(self.path, (404, ""))
        payload = body.encode("utf-8")
        self.send_response(status)
        # Deliberately no charset: the case requests decodes as Latin-1.
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def server():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def _audit_all(urls):
    from playwright.async_api import async_playwright

    async def run():
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)
            except Exception as exc:  # browser not installed
                pytest.skip(f"Chromium unavailable: {mod.error_summary(exc)}")
            try:
                return [await mod.audit(u, browser) for u in urls]
            finally:
                await browser.close()

    return asyncio.run(run())


def test_audit_end_to_end(server):
    static, injected, missing = _audit_all(
        [f"{server}/static", f"{server}/injected", f"{server}/missing"]
    )

    assert static.error is None
    assert static.rendering_debt_score == 0.0

    assert injected.error is None
    assert injected.raw_word_count == 1  # "Loading"
    assert injected.rendered_word_count == 9
    assert injected.rendering_debt_score == 1.0

    assert missing.error is not None and "404" in missing.error
    assert "\n" not in missing.error
