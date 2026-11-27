"""Tests for semantic-html-auditor.py. Pages are served from a local HTTP server."""

from __future__ import annotations

import http.server
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

CHAPTER = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "semantic_html_auditor", CHAPTER / "semantic-html-auditor.py"
)
sha = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = sha
_spec.loader.exec_module(sha)

CLEAN = """<!doctype html><html lang="en"><body>
<header><nav aria-label="Main"><a href="/">Home</a></nav></header>
<main><h1>Title</h1><h2>Section</h2><p>Text</p></main>
<footer>Footer</footer></body></html>"""


def audit_html(html: str | bytes, charset: str | None = None) -> list[str]:
    report = sha.AuditReport(url="https://example.com/")
    soup = sha.parse(html, charset)
    for check in (sha.check_lang, sha.check_headings, sha.check_landmarks,
                  sha.check_anchors, sha.check_buttons, sha.check_images):
        check(soup, report)
    return [f.rule for f in report.findings]


def page(body: str, body_attrs: str = "") -> str:
    return CLEAN.replace("<body>", f"<body {body_attrs}>").replace(
        "<p>Text</p>", body
    )


def test_clean_page_has_no_findings():
    assert audit_html(CLEAN) == []


def test_reference_template_passes():
    html = (CHAPTER / "semantic-page-template.example.html").read_bytes()
    assert audit_html(html) == []


# <template> handling -------------------------------------------------------

def test_inert_template_content_is_ignored():
    html = page("<template><h1>Row template</h1><a>x</a><img src=a></template>")
    assert audit_html(html) == []


def test_declarative_shadow_dom_is_audited():
    html = page('<x-card><template shadowrootmode="open"><h1>Card</h1>'
                "</template></x-card>")
    assert "multiple_h1" in audit_html(html)


# UI-component ancestors ----------------------------------------------------

def test_body_classes_do_not_make_every_heading_a_component():
    assert audit_html(page("", body_attrs='class="page has-sidebar modal-open"')) == []


def test_heading_inside_a_card_is_flagged():
    html = page('<div class="product-card"><h3>Widget</h3></div>')
    assert "heading_inside_ui_component" in audit_html(html)


def test_heading_inside_a_dialog_role_is_flagged():
    html = page('<div role="dialog"><h2>Sign in</h2></div>')
    assert "heading_inside_ui_component" in audit_html(html)


# Accessible names ----------------------------------------------------------

@pytest.mark.parametrize("link", [
    '<a href="/search"><svg role="img" aria-label="Search"></svg></a>',
    '<a href="/cart"><svg><title>Cart</title></svg></a>',
    '<a href="/me"><span role="img" aria-label="Account"></span></a>',
    '<a href="/"><img src="logo.svg" alt="Company"></a>',
    '<a href="/x"><span class="sr-only">Next</span></a>',
])
def test_named_icon_links_pass(link):
    assert "anchor_without_accessible_name" not in audit_html(page(link))


def test_unnamed_icon_link_is_flagged():
    html = page('<a href="/search"><svg><path d="M0 0"/></svg></a>')
    assert "anchor_without_accessible_name" in audit_html(html)


@pytest.mark.parametrize("href", ["", "#", "javascript:void(0)"])
def test_non_crawlable_href(href):
    assert "anchor_non_crawlable_href" in audit_html(page(f'<a href="{href}">Go</a>'))


def test_generic_and_missing_alt():
    rules = audit_html(page('<img src="a.jpg" alt="Product Image"><img src="b.jpg">'))
    assert rules == ["image_generic_alt", "image_missing_alt"]


# Encoding ------------------------------------------------------------------

def test_utf8_without_header_charset_is_not_garbled():
    soup = sha.parse(CLEAN.replace("Title", "Café crème").encode("utf-8"), None)
    assert soup.h1.get_text() == "Café crème"


def test_header_charset_is_honoured():
    soup = sha.parse(CLEAN.replace("Title", "Café").encode("latin-1"), "iso-8859-1")
    assert soup.h1.get_text() == "Café"


def test_header_charset_parsing():
    assert sha.header_charset('text/html; charset="UTF-8"') == "UTF-8"
    assert sha.header_charset("text/html") is None
    assert sha.header_charset(None) is None


# Fetching and main -----------------------------------------------------------

@pytest.fixture
def site():
    routes: dict[str, tuple[int, str, bytes]] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, ctype, body = routes.get(self.path, (404, "text/html", b"<h1>404</h1>"))
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield base, routes
    httpd.shutdown()


def run_main(monkeypatch, capsys, *argv):
    monkeypatch.setattr(sys, "argv", ["semantic-html-auditor.py", *argv])
    code = sha.main()
    return code, capsys.readouterr()


def test_main_exit_codes(site, monkeypatch, capsys):
    base, routes = site
    routes["/ok"] = (200, "text/html", CLEAN.encode())
    routes["/bad"] = (200, "text/html", CLEAN.replace("<h1>Title</h1>", "").encode())

    code, out = run_main(monkeypatch, capsys, "--url", f"{base}/ok")
    assert code == 0 and json.loads(out.out)["summary"]["urls_fetched"] == 1

    code, _ = run_main(monkeypatch, capsys, "--url", f"{base}/bad")
    assert code == 1


def test_unfetchable_url_is_not_a_pass(site, monkeypatch, capsys):
    base, _ = site
    code, out = run_main(monkeypatch, capsys, "--url", f"{base}/missing")
    report = json.loads(out.out)["reports"][0]
    assert code == 2
    assert report["fetched"] is False and report["status_code"] == 404


def test_high_finding_wins_over_fetch_error(site, monkeypatch, capsys, tmp_path):
    base, routes = site
    routes["/bad"] = (200, "text/html", CLEAN.replace("<main>", "<div>").encode())
    urls = tmp_path / "urls.txt"
    urls.write_text(f"# list\n{base}/bad\n{base}/missing\n")
    code, _ = run_main(monkeypatch, capsys, "--urls-file", str(urls))
    assert code == 1


@pytest.mark.parametrize("content", [None, "# only a comment\n"])
def test_bad_urls_file_exits_two(tmp_path, monkeypatch, capsys, content):
    urls = tmp_path / "urls.txt"
    if content is not None:
        urls.write_text(content)
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, capsys, "--urls-file", str(urls))
    assert exc.value.code == 2
