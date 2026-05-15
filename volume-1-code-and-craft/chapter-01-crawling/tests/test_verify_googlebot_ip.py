"""Tests for verify-googlebot-ip.py.

The script is loaded via importlib because its filename uses hyphens,
which is not a valid Python module identifier.
"""

from __future__ import annotations

import importlib.util
import io
import ssl
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "verify-googlebot-ip.py"
_spec = importlib.util.spec_from_file_location("verify_googlebot_ip", SCRIPT_PATH)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


# ip_in_ranges -----------------------------------------------------------

def test_ip_in_ranges_ipv4_match():
    assert mod.ip_in_ranges("66.249.66.1", ["66.249.64.0/19"]) is True


def test_ip_in_ranges_ipv4_miss():
    assert mod.ip_in_ranges("8.8.8.8", ["66.249.64.0/19"]) is False


def test_ip_in_ranges_ipv6_match():
    assert mod.ip_in_ranges("2001:4860:4801:1::1", ["2001:4860:4801::/48"]) is True


def test_ip_in_ranges_empty_list():
    assert mod.ip_in_ranges("8.8.8.8", []) is False


def test_ip_in_ranges_skips_none_entries():
    # fetch_ranges may emit None when a prefix has neither v4 nor v6 keys
    assert mod.ip_in_ranges("66.249.66.1", [None, "66.249.64.0/19"]) is True


def test_ip_in_ranges_rejects_malformed_ip():
    with pytest.raises(ValueError):
        mod.ip_in_ranges("not-an-ip", ["66.249.64.0/19"])


# fetch_ranges -----------------------------------------------------------

def test_fetch_ranges_parses_v4_and_v6(monkeypatch):
    payload = (
        b'{"prefixes": ['
        b'{"ipv4Prefix": "1.2.3.0/24"},'
        b'{"ipv6Prefix": "2001:db8::/32"},'
        b'{"ipv4Prefix": "5.6.7.0/24"}'
        b']}'
    )

    class FakeResponse:
        def __enter__(self):
            return io.BytesIO(payload)

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout, context):
        return FakeResponse()

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    result = mod.fetch_ranges("https://example.com/x.json", ssl.create_default_context())
    assert result == ["1.2.3.0/24", "2001:db8::/32", "5.6.7.0/24"]


# build_ssl_context ------------------------------------------------------

def test_build_ssl_context_returns_ssl_context():
    assert isinstance(mod.build_ssl_context(), ssl.SSLContext)


# main -------------------------------------------------------------------

def test_main_exits_zero_when_ip_matches(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["verify-googlebot-ip.py", "66.249.66.1"])
    monkeypatch.setattr(mod, "fetch_ranges", lambda url, ctx: ["66.249.64.0/19"])
    assert mod.main() == 0
    assert "66.249.66.1" in capsys.readouterr().out


def test_main_exits_one_when_ip_misses(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["verify-googlebot-ip.py", "8.8.8.8"])
    monkeypatch.setattr(mod, "fetch_ranges", lambda url, ctx: ["66.249.64.0/19"])
    assert mod.main() == 1


def test_main_continues_when_one_source_fails(monkeypatch, capsys):
    """If the first source raises, main should still try the next one."""
    calls = {"n": 0}

    def flaky_fetch(url, ctx):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated network failure")
        return ["66.249.64.0/19"]

    monkeypatch.setattr(sys, "argv", ["verify-googlebot-ip.py", "66.249.66.1"])
    monkeypatch.setattr(mod, "fetch_ranges", flaky_fetch)
    assert mod.main() == 0
    assert "Could not fetch" in capsys.readouterr().err
