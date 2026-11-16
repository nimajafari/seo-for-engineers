"""Behavior tests for compare-raw-vs-rendered.sh.

A stub `curl` first on PATH writes a per-user-agent body to the -o file
and prints the -w metadata, so the suite runs offline and can simulate
user-agent-adaptive serving and transport failures.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "compare-raw-vs-rendered.sh"

# The stub picks the Googlebot or browser variant by the -A value.
FAKE_CURL = r"""#!/usr/bin/env bash
ua="" out="" url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -A) ua="$2"; shift 2 ;;
    -o) out="$2"; shift 2 ;;
    -w|--max-time) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
case "$ua" in *Googlebot*) v=GB ;; *) v=BR ;; esac
fail_var="CURL_FAIL_$v"; body_var="CURL_BODY_$v"; meta_var="CURL_META_$v"
if [ -n "${!fail_var:-}" ]; then
  echo "curl: (6) Could not resolve host" >&2
  exit 6
fi
printf '%s' "${!body_var:-<html></html>}" > "$out"
printf '%s' "${!meta_var:-200 $url}"
"""


@pytest.fixture
def stub_path(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def run(stub_path, *args, **env):
    full_env = {**os.environ, "PATH": f"{stub_path}{os.pathsep}{os.environ['PATH']}"}
    full_env.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True,
        env=full_env, timeout=30,
    )


def test_identical_responses(stub_path):
    r = run(stub_path, "https://example.com/")
    assert r.returncode == 0, r.stderr
    assert "Googlebot: HTTP 200  https://example.com/" in r.stdout
    assert "Bodies are identical." in r.stdout
    # Both bodies are still printed when no out-dir is given.
    assert r.stdout.count("<html></html>") == 2


def test_status_difference_is_flagged(stub_path):
    r = run(stub_path, "https://example.com/",
            CURL_META_GB="403 https://example.com/")
    assert r.returncode == 0
    assert "Googlebot: HTTP 403" in r.stdout
    assert "Browser:   HTTP 200" in r.stdout
    assert "differs by user-agent" in r.stdout


def test_redirect_target_difference_is_flagged(stub_path):
    r = run(stub_path, "https://example.com/",
            CURL_META_BR="200 https://example.com/en/")
    assert "differs by user-agent" in r.stdout


def test_body_difference_is_reported(stub_path):
    r = run(stub_path, "https://example.com/",
            CURL_BODY_GB="<p>server rendered</p>", CURL_BODY_BR="<div id=app></div>")
    assert "Bodies differ" in r.stdout


def test_out_dir_saves_bodies_without_printing_them(stub_path, tmp_path):
    out = tmp_path / "out"
    r = run(stub_path, "https://example.com/", str(out),
            CURL_BODY_GB="googlebot body", CURL_BODY_BR="browser body")
    assert r.returncode == 0, r.stderr
    assert (out / "googlebot.html").read_text() == "googlebot body"
    assert (out / "browser.html").read_text() == "browser body"
    assert "googlebot body" not in r.stdout
    assert "Saved:" in r.stdout


@pytest.mark.parametrize("failing", ["CURL_FAIL_GB", "CURL_FAIL_BR"])
def test_transport_failure_exits_two(stub_path, failing):
    r = run(stub_path, "https://example.invalid/", **{failing: "1"})
    assert r.returncode == 2
    assert "failed" in r.stderr
    assert "Summary" not in r.stdout


@pytest.mark.parametrize("args", [[], ["a", "b", "c"]])
def test_usage_errors(stub_path, args):
    r = run(stub_path, *args)
    assert r.returncode == 1
    assert "Usage" in r.stderr
