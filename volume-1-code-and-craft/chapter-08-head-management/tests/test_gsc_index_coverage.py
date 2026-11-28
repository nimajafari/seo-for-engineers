"""Tests for gsc-index-coverage.py. The Search Console client is faked,
so neither the Google libraries nor network access are needed."""

from __future__ import annotations

import json
import sys

import pytest
from conftest import load_script

gsc = load_script("gsc-index-coverage.py", "gsc_index_coverage")


class FakeService:
    """Mimics service.urlInspection().index().inspect(body=...).execute()."""

    def __init__(self, responses):
        self.responses = responses
        self.bodies = []

    def urlInspection(self):
        return self

    def index(self):
        return self

    def inspect(self, body):
        self.bodies.append(body)
        self._next = self.responses[body["inspectionUrl"]]
        return self

    def execute(self):
        if isinstance(self._next, Exception):
            raise self._next
        return self._next


RESULT = {
    "inspectionResult": {
        "indexStatusResult": {
            "verdict": "PASS",
            "coverageState": "Submitted and indexed",
            "robotsTxtState": "ALLOWED",
            "indexingState": "INDEXING_ALLOWED",
            "googleCanonical": "https://e.com/a",
            "userCanonical": "https://e.com/a",
            "lastCrawlTime": "2026-11-20T10:00:00Z",
            "pageFetchState": "SUCCESSFUL",
        }
    }
}


def test_module_imports_without_google_libraries():
    assert callable(gsc.inspect_one)


def test_inspect_one_flattens_the_response():
    service = FakeService({"https://e.com/a": RESULT})
    row = gsc.inspect_one(service, "sc-domain:e.com", "https://e.com/a")
    assert service.bodies == [{"inspectionUrl": "https://e.com/a", "siteUrl": "sc-domain:e.com"}]
    assert row["verdict"] == "PASS" and row["google_canonical"] == "https://e.com/a"


def test_inspect_one_tolerates_an_empty_result():
    row = gsc.inspect_one(FakeService({"https://e.com/a": {}}), "s", "https://e.com/a")
    assert row["url"] == "https://e.com/a" and row["verdict"] is None


def run_main(monkeypatch, capsys, service, *argv):
    monkeypatch.setattr(gsc, "load_credentials", lambda path: object())
    monkeypatch.setattr(gsc, "build_service", lambda creds: service)
    monkeypatch.setattr(sys, "argv", ["gsc-index-coverage.py", "--site", "sc-domain:e.com",
                                      "--service-account", "key.json", *argv])
    code = gsc.main()
    return code, capsys.readouterr()


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    urls = tmp_path / "urls.txt"
    urls.write_text("# c\nhttps://e.com/a\n\nhttps://e.com/b\n")
    service = FakeService({"https://e.com/a": RESULT, "https://e.com/b": RuntimeError("quota")})
    code, out = run_main(monkeypatch, capsys, service, "--urls-file", str(urls))
    rows = json.loads(out.out)
    assert code == 1
    assert rows[0]["verdict"] == "PASS" and rows[1] == {"url": "https://e.com/b", "error": "quota"}

    code, _ = run_main(monkeypatch, capsys, FakeService({"https://e.com/a": RESULT}),
                       "--url", "https://e.com/a")
    assert code == 0


@pytest.mark.parametrize("content", [None, "# only a comment\n"])
def test_bad_urls_file_exits_two(tmp_path, monkeypatch, capsys, content):
    urls = tmp_path / "urls.txt"
    if content is not None:
        urls.write_text(content)
    with pytest.raises(SystemExit) as exc:
        run_main(monkeypatch, capsys, FakeService({}), "--urls-file", str(urls))
    assert exc.value.code == 2


def test_unloadable_key_exits_two(monkeypatch, capsys):
    def fail(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(gsc, "load_credentials", fail)
    monkeypatch.setattr(sys, "argv", ["gsc-index-coverage.py", "--site", "s", "--url",
                                      "https://e.com/a", "--service-account", "missing.json"])
    assert gsc.main() == 2
    assert "cannot load service-account key" in capsys.readouterr().err
