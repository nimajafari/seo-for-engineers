"""
conftest.py

pytest configuration for the chapter-17 head-tag assertion suite.

Registers the --base-url and --robots-url command-line options used
by the HTTP-mode tests in test_facet_head_tags.py. pytest only picks
up pytest_addoption hooks from conftest.py files, not from individual
test files.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--base-url", action="store", default=None,
        help="Live origin to test against. If unset, HTTP-mode tests skip.",
    )
    parser.addoption(
        "--robots-url", action="store", default=None,
        help="robots.txt URL for the live origin used by the robots checks.",
    )


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def robots_url(request):
    return request.config.getoption("--robots-url")
