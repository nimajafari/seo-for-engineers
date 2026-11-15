"""Behavior tests for the chapter's shell scripts.

Each test puts a stub `dig` or `curl` first on PATH, so the suite runs
offline and can simulate failures (resolver timeouts, unreachable hosts)
that are hard to trigger against the real network.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

CHAPTER = Path(__file__).resolve().parent.parent


def write_stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def run(script: str, *args: str, stub_dir: Path, env: dict | None = None):
    full_env = {**os.environ, "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}"}
    full_env.update(env or {})
    return subprocess.run(
        ["bash", str(CHAPTER / script), *args],
        capture_output=True,
        text=True,
        env=full_env,
        timeout=30,
    )


# verify-googlebot.sh ----------------------------------------------------

# Stub dig: answers depend on the query type, and DIG_FAIL makes one kind
# of query behave like a resolver timeout (";;" on stdout, exit 9).
FAKE_DIG = r"""
args="$*"
case "$args" in
  *-x*)   kind=ptr ;;
  *AAAA*) kind=aaaa ;;
  *)      kind=a ;;
esac
if [ "${DIG_FAIL:-}" = "$kind" ]; then
  echo ";; connection timed out; no servers could be reached"
  exit 9
fi
case "$kind" in
  ptr)  printf '%b' "${DIG_PTR:-}" ;;
  a)    printf '%b' "${DIG_A:-}" ;;
  aaaa) printf '%b' "${DIG_AAAA:-}" ;;
esac
exit 0
"""


@pytest.fixture
def dig_stub(tmp_path):
    write_stub(tmp_path, "dig", FAKE_DIG)
    return tmp_path


def test_verify_googlebot_passes_genuine_ip(dig_stub):
    result = run(
        "verify-googlebot.sh", "66.249.66.1", stub_dir=dig_stub,
        env={"DIG_PTR": "crawl-66-249-66-1.googlebot.com.\n",
             "DIG_A": "66.249.66.1\n"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "verified Googlebot" in result.stdout


def test_verify_googlebot_matches_ipv6_via_aaaa(dig_stub):
    result = run(
        "verify-googlebot.sh", "2001:4860:4801:10::1", stub_dir=dig_stub,
        env={"DIG_PTR": "crawl-2001-4860-4801-10--1.googlebot.com.\n",
             "DIG_AAAA": "2001:4860:4801:10::1\n"},
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_googlebot_rejects_foreign_domain(dig_stub):
    result = run(
        "verify-googlebot.sh", "8.8.8.8", stub_dir=dig_stub,
        env={"DIG_PTR": "dns.google.\n"},
    )
    assert result.returncode == 1


def test_verify_googlebot_rejects_lookalike_domain(dig_stub):
    result = run(
        "verify-googlebot.sh", "203.0.113.5", stub_dir=dig_stub,
        env={"DIG_PTR": "crawl.googlebot.com.evil.example.\n"},
    )
    assert result.returncode == 1


def test_verify_googlebot_rejects_forward_mismatch(dig_stub):
    result = run(
        "verify-googlebot.sh", "203.0.113.5", stub_dir=dig_stub,
        env={"DIG_PTR": "crawl-66-249-66-1.googlebot.com.\n",
             "DIG_A": "66.249.66.1\n"},
    )
    assert result.returncode == 1
    assert "Possible spoof" in result.stdout


def test_verify_googlebot_missing_ptr_is_not_verified(dig_stub):
    result = run("verify-googlebot.sh", "203.0.113.5", stub_dir=dig_stub)
    assert result.returncode == 1
    assert "No reverse DNS" in result.stdout


@pytest.mark.parametrize("failing_query", ["ptr", "a", "aaaa"])
def test_verify_googlebot_dns_failure_is_indeterminate(dig_stub, failing_query):
    # A resolver timeout must exit 2, not 1, and the ";;" diagnostic must
    # never be treated as a hostname or an address.
    result = run(
        "verify-googlebot.sh", "66.249.66.1", stub_dir=dig_stub,
        env={"DIG_PTR": "crawl-66-249-66-1.googlebot.com.\n",
             "DIG_A": "66.249.66.1\n",
             "DIG_FAIL": failing_query},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "DNS query failed" in result.stderr


def test_verify_googlebot_without_dig_is_indeterminate(tmp_path):
    # Shadow dig with a PATH that has bash but no dig.
    bash_dir = tmp_path / "bin"
    bash_dir.mkdir()
    for tool in ("bash", "sed", "grep", "printf"):
        found = subprocess.run(["which", tool], capture_output=True, text=True).stdout.strip()
        if found:
            (bash_dir / tool).symlink_to(found)
    result = subprocess.run(
        [str(bash_dir / "bash"), str(CHAPTER / "verify-googlebot.sh"), "66.249.66.1"],
        capture_output=True, text=True, env={"PATH": str(bash_dir)}, timeout=30,
    )
    assert result.returncode == 2
    assert "dig is not installed" in result.stderr


# http2-check.sh ---------------------------------------------------------

# Stub curl: prints CURL_OUT (the -w output) and exits CURL_EXIT.
FAKE_CURL = r"""
if [ "${CURL_EXIT:-0}" != 0 ]; then
  echo "curl: (6) Could not resolve host" >&2
  exit "$CURL_EXIT"
fi
printf '%b' "${CURL_OUT:-}"
"""


@pytest.fixture
def curl_stub(tmp_path):
    write_stub(tmp_path, "curl", FAKE_CURL)
    return tmp_path


def test_http2_check_detects_http2(curl_stub):
    result = run("http2-check.sh", "https://example.com", stub_dir=curl_stub,
                 env={"CURL_OUT": "2"})
    assert result.returncode == 0
    assert "Protocol: HTTP/2" in result.stdout


def test_http2_check_reports_http11(curl_stub):
    result = run("http2-check.sh", "https://example.com", stub_dir=curl_stub,
                 env={"CURL_OUT": "1.1"})
    assert result.returncode == 1
    assert "Not serving HTTP/2" in result.stdout


def test_http2_check_request_failure_is_distinct(curl_stub):
    result = run("http2-check.sh", "https://example.invalid", stub_dir=curl_stub,
                 env={"CURL_EXIT": "6"})
    assert result.returncode == 2
    assert "failed" in result.stderr


# ttfb-benchmark.sh ------------------------------------------------------

def test_ttfb_benchmark_prints_status_and_timings(curl_stub):
    out = ("HTTP:  200\nDNS:   0.01s\nTCP:   0.02s\nTLS:   0.05s\n"
           "TTFB:  0.12s\nTotal: 0.20s\n")
    result = run("ttfb-benchmark.sh", "https://example.com", stub_dir=curl_stub,
                 env={"CURL_OUT": out})
    assert result.returncode == 0
    assert "HTTP:  200" in result.stdout
    assert "TTFB:  0.12s" in result.stdout


def test_ttfb_benchmark_failure_prints_no_timings(curl_stub):
    result = run("ttfb-benchmark.sh", "https://example.invalid", stub_dir=curl_stub,
                 env={"CURL_EXIT": "6"})
    assert result.returncode == 2
    assert "TTFB" not in result.stdout


@pytest.mark.parametrize(
    "script", ["verify-googlebot.sh", "http2-check.sh", "ttfb-benchmark.sh"]
)
def test_scripts_require_an_argument(script, tmp_path):
    result = run(script, stub_dir=tmp_path)
    assert result.returncode == 1
    assert "Usage" in result.stderr
