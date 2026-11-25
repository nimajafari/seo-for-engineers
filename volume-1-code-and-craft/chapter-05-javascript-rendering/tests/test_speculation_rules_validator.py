"""Tests for speculation-rules-validator.py."""

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
    "speculation_rules_validator", CHAPTER / "speculation-rules-validator.py"
)
v = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = v
_spec.loader.exec_module(v)


def findings(rules, origin=None):
    return v.validate(rules, page_origin=origin).findings


def severities(rules, origin=None):
    return sorted(f.severity for f in findings(rules, origin))


# Polarity of "not" clauses -----------------------------------------------

CHROME_RECOMMENDED = {
    "prerender": [{
        "where": {"and": [
            {"href_matches": "/*"},
            {"not": {"href_matches": "/logout"}},
            {"not": {"selector_matches": ".no-prerender"}},
        ]},
        "eagerness": "moderate",
    }]
}


def test_excluded_action_page_is_not_flagged():
    # The safe, recommended shape used to fail CI as a HIGH finding.
    assert findings(CHROME_RECOMMENDED) == []


def test_targeted_action_page_is_flagged():
    rules = {"prerender": [{"urls": ["/checkout?step=1"], "eagerness": "moderate"}]}
    assert severities(rules) == ["high"]


def test_double_negation_is_a_target_again():
    rules = {"prerender": [{
        "where": {"not": {"not": {"href_matches": "/logout"}}},
        "eagerness": "moderate",
    }]}
    assert any("one-time-action" in f.message for f in findings(rules))


def test_collect_patterns_splits_targets_and_exclusions():
    rule = CHROME_RECOMMENDED["prerender"][0]
    assert v.collect_url_patterns(rule) == ["/*"]
    assert v.collect_excluded_patterns(rule) == ["/logout", "selector:.no-prerender"]


def test_broad_prerender_without_exclusions_gets_low_hint():
    rules = {"prerender": [{"where": {"href_matches": "/*"}, "eagerness": "moderate"}]}
    assert severities(rules) == ["low"]


# URLPattern objects in href_matches ---------------------------------------

def test_url_pattern_object_is_checked():
    rules = {"prerender": [{
        "where": {"href_matches": {"pathname": "/cart/*"}},
        "eagerness": "moderate",
    }]}
    assert any("one-time-action" in f.message for f in findings(rules))


def test_url_pattern_object_with_host_is_cross_origin():
    rules = {"prefetch": [{
        "where": {"href_matches": {"protocol": "https", "hostname": "cdn.other.example",
                                   "pathname": "/a/*"}},
        "eagerness": "moderate",
    }]}
    msgs = [f.message for f in findings(rules, origin="https://example.com")]
    assert any("cross-origin" in m for m in msgs)


# Eagerness ----------------------------------------------------------------

def test_missing_eagerness_on_list_rule_defaults_to_immediate():
    assert severities({"prefetch": [{"urls": ["/a"]}]}) == ["medium"]


def test_missing_eagerness_on_document_rule_is_conservative():
    rules = {"prefetch": [{"where": {"href_matches": "/a"}}]}
    assert findings(rules) == []


def test_invalid_eagerness():
    rules = {"prefetch": [{"urls": ["/a"], "eagerness": "aggressive"}]}
    assert any("not a valid value" in f.message for f in findings(rules))


def test_immediate_broad_prerender_is_high():
    rules = {"prerender": [{
        "where": {"and": [{"href_matches": "/*"}, {"not": {"href_matches": "/logout"}}]},
        "eagerness": "immediate",
    }]}
    assert "high" in severities(rules)


def test_immediate_selector_prerender_is_high():
    rules = {"prerender": [{"where": {"selector_matches": ".card a"}, "eagerness": "immediate"}]}
    assert any("selector_matches" in f.message for f in findings(rules))


def test_example_file_has_no_high_findings():
    rules = v.load_rules_from_file(CHAPTER / "example-speculation-rules.json")
    assert not v.validate(rules).has_high_severity


# Fetching from a URL -------------------------------------------------------

class _Site:
    def __init__(self):
        self.routes: dict[str, tuple[int, dict, bytes]] = {}

    def add(self, path, body, status=200, headers=None):
        payload = body if isinstance(body, bytes) else body.encode("utf-8")
        self.routes[path] = (status, headers or {"Content-Type": "text/html"}, payload)


@pytest.fixture
def site():
    s = _Site()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, headers, body = s.routes.get(self.path, (404, {}, b""))
            self.send_response(status)
            for k, val in headers.items():
                self.send_header(k, val)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05},
                     daemon=True).start()
    s.origin = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield s
    httpd.shutdown()


def page_with(*scripts):
    tags = "".join(f'<script type="speculationrules">{x}</script>' for x in scripts)
    return f"<html><head>{tags}</head><body></body></html>"


def test_merges_every_script(site):
    a = json.dumps({"prefetch": [{"urls": ["/a"], "eagerness": "moderate"}]})
    b = json.dumps({"prerender": [{"urls": ["/b"], "eagerness": "moderate"}]})
    site.add("/", page_with(a, b))
    rules, origin, problems = v.fetch_rules_from_url(site.origin + "/")
    assert set(rules) == {"prefetch", "prerender"}
    assert origin == site.origin and problems == []


def test_invalid_script_is_reported_not_fatal(site):
    good = json.dumps({"prefetch": [{"urls": ["/a"], "eagerness": "moderate"}]})
    site.add("/", page_with("{not json", good))
    rules, _, problems = v.fetch_rules_from_url(site.origin + "/")
    assert rules["prefetch"]
    assert len(problems) == 1 and "#1 is ignored" in problems[0]


def test_speculation_rules_header_is_followed(site):
    rules_json = json.dumps({"prerender": [{"urls": ["/cart"], "eagerness": "moderate"}]})
    site.add("/rules.json", rules_json,
             headers={"Content-Type": "application/speculationrules+json"})
    site.add("/", "<html><body>no inline rules</body></html>",
             headers={"Content-Type": "text/html",
                      "Speculation-Rules": '"/rules.json", "/missing.json"'})
    rules, _, problems = v.fetch_rules_from_url(site.origin + "/")
    assert rules["prerender"][0]["urls"] == ["/cart"]
    assert any("missing.json" in p for p in problems)
    report = v.validate(rules, page_origin=site.origin)
    assert report.has_high_severity  # /cart from the header file is caught


def test_header_rule_urls_parsing():
    assert v.header_rule_urls('"/a.json", "https://cdn.example/b.json"',
                              "https://example.com/page") == [
        "https://example.com/a.json", "https://cdn.example/b.json"]
    assert v.header_rule_urls(None, "https://example.com/") == []


def test_page_without_any_rules_errors(site):
    site.add("/", "<html><body></body></html>")
    with pytest.raises(ValueError, match="no <script"):
        v.fetch_rules_from_url(site.origin + "/")


# main ---------------------------------------------------------------------

def run_main(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["speculation-rules-validator.py", *argv])
    return v.main()


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    safe = tmp_path / "safe.json"
    safe.write_text(json.dumps(CHROME_RECOMMENDED))
    assert run_main(monkeypatch, "--file", str(safe)) == 0

    risky = tmp_path / "risky.json"
    risky.write_text(json.dumps({"prerender": [{"urls": ["/logout"], "eagerness": "moderate"}]}))
    assert run_main(monkeypatch, "--file", str(risky)) == 1

    not_object = tmp_path / "list.json"
    not_object.write_text("[]")
    assert run_main(monkeypatch, "--file", str(not_object)) == 2


def test_main_prints_ignored_sources(site, monkeypatch, capsys):
    site.add("/", page_with("{broken"))
    assert run_main(monkeypatch, "--url", site.origin + "/") == 0
    assert "IGNORED rule sources (1)" in capsys.readouterr().out
