"""Tests for crux-fetcher.py. All CrUX API calls are mocked."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest
import requests

SCRIPT = Path(__file__).resolve().parent.parent / "crux-fetcher.py"
_spec = importlib.util.spec_from_file_location("crux_fetcher", SCRIPT)
cf = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cf
_spec.loader.exec_module(cf)

KEY = "AIzaTESTKEY123"

RECORD = {
    "key": {"url": "https://example.com/"},
    "metrics": {
        "largest_contentful_paint": {
            "histogram": [
                {"start": 0, "end": 2500, "density": 0.8},
                {"start": 2500, "end": 4000, "density": 0.15},
                {"start": 4000, "density": 0.05},
            ],
            "percentiles": {"p75": 2100},
        },
        "interaction_to_next_paint": {
            "histogram": [
                {"start": 0, "end": 200, "density": 0.9},
                {"start": 200, "end": 500, "density": 0.07},
                {"start": 500, "density": 0.03},
            ],
            "percentiles": {"p75": 150},
        },
        "cumulative_layout_shift": {
            "histogram": [
                {"start": "0.00", "end": "0.10", "density": 0.7},
                {"start": "0.10", "end": "0.25", "density": 0.2},
                {"start": "0.25", "density": 0.1},
            ],
            "percentiles": {"p75": "0.08"},
        },
    },
    "collectionPeriod": {
        "firstDate": {"year": 2026, "month": 10, "day": 18},
        "lastDate": {"year": 2026, "month": 11, "day": 14},
    },
}


class FakeResponse:
    def __init__(self, status, payload=None, headers=None, text=""):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def calls(monkeypatch):
    """Record requests.post calls; responses come from a queue."""
    log = {"calls": [], "queue": []}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        log["calls"].append({"url": url, "headers": headers, "params": params, "json": json})
        item = log["queue"].pop(0) if log["queue"] else FakeResponse(200, {"record": RECORD})
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(cf.requests, "post", fake_post)
    monkeypatch.setattr(cf.time, "sleep", lambda s: None)
    return log


def test_extract_metrics_and_period():
    metrics = cf.extract_metrics(RECORD)
    assert metrics["lcp"] == {"p75": 2100.0, "good_pct": 80.0, "ni_pct": 15.0, "poor_pct": 5.0}
    assert metrics["cls"]["p75"] == 0.08
    assert cf.extract_collection_period_end(RECORD) == "2026-11-14"


def test_key_is_sent_in_header_not_url(calls):
    r = cf.fetch_one(KEY, "https://example.com/", None, False)
    assert r.has_data
    call = calls["calls"][0]
    assert call["headers"] == {"X-Goog-Api-Key": KEY}
    assert not call["params"]
    assert KEY not in call["url"]
    assert call["json"] == {"url": "https://example.com/"}


def test_connection_error_never_carries_the_key(calls):
    leaky = requests.ConnectionError(f"Max retries exceeded with url: /x?key={KEY}")
    calls["queue"] = [leaky] * (cf.MAX_RETRIES + 1)
    r = cf.fetch_one(KEY, "https://example.com/", None, False)
    assert r.error and KEY not in r.error
    assert "<redacted>" in r.error


def test_api_error_message_is_surfaced(calls):
    calls["queue"] = [FakeResponse(400, {"error": {"message": "API key not valid."}})]
    r = cf.fetch_one(KEY, "https://example.com/", None, False)
    assert r.error == "HTTP 400: API key not valid."


def test_404_means_no_data_not_error(calls):
    calls["queue"] = [FakeResponse(404, {"error": {"message": "chrome ux report data not found"}})]
    r = cf.fetch_one(KEY, "https://example.com/rare", None, False)
    assert not r.has_data and r.error is None


def test_retries_429_then_succeeds(calls):
    calls["queue"] = [FakeResponse(429, headers={"Retry-After": "2"})]
    r = cf.fetch_one(KEY, "https://example.com/", "PHONE", False)
    assert r.has_data and r.form_factor == "PHONE"
    assert len(calls["calls"]) == 2
    assert calls["calls"][0]["json"]["formFactor"] == "PHONE"


def test_origin_mode_shares_one_query_per_origin(calls):
    cache = {}
    for path in ("/a", "/b", "/c"):
        r = cf.fetch_one(KEY, f"https://example.com{path}", None, True, cache=cache)
        assert r.has_data
    cf.fetch_one(KEY, "https://other.example/", None, True, cache=cache)
    assert [c["json"] for c in calls["calls"]] == [
        {"origin": "https://example.com"},
        {"origin": "https://other.example"},
    ]


def test_non_absolute_url_is_rejected_without_a_call(calls):
    r = cf.fetch_one(KEY, "example.com/page", None, False)
    assert r.error == "not an absolute http(s) URL"
    assert calls["calls"] == []


def test_main_batch_csv(calls, tmp_path, monkeypatch):
    urls = tmp_path / "urls.txt"
    urls.write_text("# list\nhttps://example.com/\nhttps://example.com/rare\n")
    out = tmp_path / "r.csv"
    calls["queue"] = [FakeResponse(200, {"record": RECORD}), FakeResponse(404, {})]
    monkeypatch.setenv("CRUX_API_KEY", KEY)
    monkeypatch.setattr(sys, "argv", ["crux-fetcher.py", "--urls", str(urls), "--csv", str(out)])
    assert cf.main() == 0
    rows = list(csv.DictReader(out.open()))
    assert [r["has_data"] for r in rows] == ["yes", "no"]
    assert rows[0]["lcp_p75"] == "2100.0" and rows[0]["collection_period_end"] == "2026-11-14"


@pytest.mark.parametrize("content", [None, "# nothing\n"])
def test_main_bad_urls_file_exits_two(tmp_path, monkeypatch, content):
    urls = tmp_path / "urls.txt"
    if content is not None:
        urls.write_text(content)
    monkeypatch.setenv("CRUX_API_KEY", KEY)
    monkeypatch.setattr(sys, "argv", ["crux-fetcher.py", "--urls", str(urls), "--csv", "x.csv"])
    assert cf.main() == 2


def test_main_requires_key(monkeypatch):
    monkeypatch.delenv("CRUX_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["crux-fetcher.py", "https://example.com/"])
    assert cf.main() == 2
