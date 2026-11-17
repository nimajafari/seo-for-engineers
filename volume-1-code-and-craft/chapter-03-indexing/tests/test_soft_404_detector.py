"""Tests for soft-404-detector.py."""

from __future__ import annotations

import csv
import sys

import pytest

from conftest import Route, load_script

sd = load_script("soft-404-detector.py", "soft_404_detector")

LONG_TEXT = " ".join(f"word{i}" for i in range(120))


def html(body: str) -> str:
    return f"<html><head><title>t</title></head><body>{body}</body></html>"


def detect(serve, routes, path, min_words=50):
    origin = serve(routes)
    return sd.detect(origin + path, min_words=min_words, phrases=sd.DEFAULT_SOFT_404_PHRASES)


# units ------------------------------------------------------------------

def test_count_words_handles_unspaced_scripts():
    assert sd.count_words("hello world") == 2
    assert sd.count_words("東京タワー") == 5
    assert sd.count_words("Tokyo 東京") == 3


def test_extract_visible_text_decodes_like_a_browser():
    body = '<html><head><meta charset="utf-8"></head><body>Página no encontrada</body></html>'
    text = sd.extract_visible_text(body.encode("utf-8"), "text/html")
    assert "Página" in text


def test_extract_visible_text_drops_scripts():
    text = sd.extract_visible_text(b"<body>shown<script>hidden()</script></body>")
    assert text == "shown"


@pytest.mark.parametrize(
    "requested, final, redirected, expected",
    [
        ("https://e.com/old", "https://e.com/", True, True),
        ("https://e.com/old", "https://e.com", True, True),
        ("https://e.com/old", "https://e.com/new", True, False),
        ("https://e.com/", "https://e.com/", True, False),
        ("https://e.com/old", "https://e.com/", False, False),
    ],
)
def test_redirected_to_root(requested, final, redirected, expected):
    assert sd.redirected_to_root(requested, final, redirected) is expected


# detect end to end ------------------------------------------------------

def test_thin_page_with_error_phrase_has_both_signals(serve):
    r = detect(serve, {"/s": Route(html("No results found"))}, "/s")
    assert r.is_suspect
    assert r.signals == ["thin_content", "error_phrase"]
    assert r.matched_phrases == ["no results found"]


def test_long_page_without_phrase_is_clean(serve):
    r = detect(serve, {"/p": Route(html(LONG_TEXT))}, "/p")
    assert not r.is_suspect
    assert r.signals == []


def test_long_page_with_phrase_has_single_signal(serve):
    r = detect(serve, {"/p": Route(html(LONG_TEXT + " Out of stock"))}, "/p")
    assert r.signals == ["error_phrase"]


def test_redirect_of_removed_page_to_home_is_flagged(serve):
    routes = {
        "/discontinued": Route(status=301, headers={"Location": "/"}),
        "/": Route(html(LONG_TEXT)),
    }
    r = detect(serve, routes, "/discontinued")
    assert r.status_code == 200
    assert r.final_url.endswith("/")
    assert r.signals == ["redirected_to_root"]


def test_redirect_to_another_page_is_not_flagged(serve):
    routes = {
        "/old": Route(status=301, headers={"Location": "/new"}),
        "/new": Route(html(LONG_TEXT)),
    }
    assert detect(serve, routes, "/old").signals == []


def test_japanese_page_is_not_thin(serve):
    text = "東京タワーは日本の東京都港区芝公園にある総合電波塔です。" * 3
    r = detect(serve, {"/ja": Route(html(text))}, "/ja")
    assert "thin_content" not in r.signals


def test_real_404_is_not_a_soft_404(serve):
    r = detect(serve, {}, "/missing")
    assert r.status_code == 404
    assert not r.is_suspect


def test_request_failure_is_error_not_suspect():
    r = sd.detect("http://127.0.0.1:9/", 50, sd.DEFAULT_SOFT_404_PHRASES)
    assert r.error and not r.is_suspect


# main -------------------------------------------------------------------

def test_main_batch_csv_includes_signals(serve, tmp_path, monkeypatch):
    origin = serve({"/ok": Route(html(LONG_TEXT)), "/empty": Route(html("Nothing"))})
    urls = tmp_path / "urls.txt"
    urls.write_text(f"{origin}/ok\n{origin}/empty\n")
    out = tmp_path / "r.csv"
    monkeypatch.setattr(sys, "argv", ["soft-404-detector.py", "--urls", str(urls), "--csv", str(out)])
    assert sd.main() == 1
    rows = list(csv.DictReader(out.open()))
    assert [r["is_suspect"] for r in rows] == ["no", "yes"]
    assert rows[1]["signals"] == "thin_content"


def test_main_custom_phrase_file(serve, tmp_path, monkeypatch, capsys):
    origin = serve({"/p": Route(html(LONG_TEXT + " sold out forever"))})
    phrases = tmp_path / "phrases.txt"
    phrases.write_text("# custom\nsold out forever\n")
    monkeypatch.setattr(sys, "argv", ["soft-404-detector.py", f"{origin}/p", "--phrases", str(phrases)])
    assert sd.main() == 1
    assert "sold out forever" in capsys.readouterr().out


@pytest.mark.parametrize(
    "extra",
    [
        ["--urls", "MISSING", "--csv", "x.csv"],
        ["http://e.com/", "--phrases", "MISSING"],
        ["http://e.com/", "--min-words", "-1"],
    ],
)
def test_main_bad_input_exits_two(tmp_path, monkeypatch, extra):
    extra = [str(tmp_path / "nope") if a == "MISSING" else a for a in extra]
    monkeypatch.setattr(sys, "argv", ["soft-404-detector.py", *extra])
    assert sd.main() == 2
