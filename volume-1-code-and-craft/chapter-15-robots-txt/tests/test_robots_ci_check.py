"""
Unit tests for robots-ci-check.py.

Exercises the parser, the group-selection / same-token merge rules,
path matching, sanity checks, and the assertion-suite runner against
hand-crafted robots.txt fragments that target each rule.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

THIS_DIR = Path(__file__).resolve().parent
CHAPTER_DIR = THIS_DIR.parent


def _load_ci_module():
    spec = importlib.util.spec_from_file_location(
        'robots_ci_check', CHAPTER_DIR / 'robots-ci-check.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CI = _load_ci_module()


SHIPPING_ROBOTS = """\
User-agent: *
Disallow: /admin/
Disallow: /cart
Disallow: /account/
Disallow: /search

User-agent: Googlebot
Disallow: /admin/
Disallow: /cart
Disallow: /account/
Disallow: /search

User-agent: Googlebot-Image
Allow: /images/

Sitemap: https://www.example.com/sitemap.xml
"""


# ----- Parsing -----------------------------------------------------------


def test_parser_collects_groups_and_sitemaps():
    parsed = CI.parse_robots(SHIPPING_ROBOTS)
    assert len(parsed.groups) == 3
    assert parsed.groups[0].user_agents == ['*']
    assert parsed.groups[1].user_agents == ['Googlebot']
    assert parsed.groups[2].user_agents == ['Googlebot-Image']
    assert parsed.sitemaps == [
        ('https://www.example.com/sitemap.xml', len(SHIPPING_ROBOTS.splitlines())),
    ]


def test_parser_strips_comments_and_blank_lines():
    text = """\
# top-level comment
User-agent: Googlebot   # inline
Disallow: /admin/  # trailing
"""
    parsed = CI.parse_robots(text)
    assert len(parsed.groups) == 1
    assert parsed.groups[0].user_agents == ['Googlebot']
    assert parsed.groups[0].rules[0].path == '/admin/'


def test_parser_treats_blank_line_as_group_terminator():
    text = """\
User-agent: A
Disallow: /a

User-agent: B
Disallow: /b
"""
    parsed = CI.parse_robots(text)
    assert [g.user_agents for g in parsed.groups] == [['A'], ['B']]


def test_parser_accepts_multiple_user_agents_in_one_group():
    text = """\
User-agent: A
User-agent: B
Disallow: /shared
"""
    parsed = CI.parse_robots(text)
    assert len(parsed.groups) == 1
    assert parsed.groups[0].user_agents == ['A', 'B']
    assert len(parsed.groups[0].rules) == 1


# ----- Path matching -----------------------------------------------------


@pytest.mark.parametrize(
    'pattern,url_path,expected',
    [
        ('/admin/', '/admin/', True),
        ('/admin/', '/admin/users', True),
        ('/admin/', '/administration', False),
        ('/cart', '/cart', True),
        ('/cart', '/cart/checkout', True),
        ('/*.pdf$', '/files/report.pdf', True),
        ('/*.pdf$', '/files/report.pdf?v=1', False),
        ('/search', '/search?q=anything', True),
    ],
)
def test_path_matches(pattern, url_path, expected):
    assert CI.path_matches(pattern, url_path) is expected


# ----- Group selection and same-token merge ------------------------------


def test_googlebot_picks_googlebot_group_over_wildcard():
    parsed = CI.parse_robots(SHIPPING_ROBOTS)
    group = CI.select_group_for_user_agent(parsed, 'Googlebot')
    assert group is not None
    assert group.user_agents == ['googlebot']


def test_unknown_user_agent_falls_back_to_wildcard():
    parsed = CI.parse_robots(SHIPPING_ROBOTS)
    group = CI.select_group_for_user_agent(parsed, 'AcmeBot')
    assert group is not None
    assert group.user_agents == ['*']


def test_same_token_merge_across_multiple_groups():
    """
    Regression: when the winning group contains multiple User-agent
    tokens, the merge step must use the matched token, not the first
    token. Without the fix, group 2's rule was silently dropped.
    """
    text = """\
User-agent: Mediapartners-Google
User-agent: Googlebot
Disallow: /a

User-agent: Googlebot
Disallow: /b
"""
    parsed = CI.parse_robots(text)
    assert CI.is_allowed(parsed, 'Googlebot', 'https://x/a') is False
    assert CI.is_allowed(parsed, 'Googlebot', 'https://x/b') is False
    assert CI.is_allowed(parsed, 'Googlebot', 'https://x/c') is True


def test_multiple_wildcard_groups_are_merged():
    text = """\
User-agent: *
Disallow: /a

User-agent: *
Disallow: /b
"""
    parsed = CI.parse_robots(text)
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/a') is False
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/b') is False
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/c') is True


# ----- Allow / Disallow precedence ---------------------------------------


def test_allow_wins_over_disallow_at_equal_specificity():
    text = """\
User-agent: *
Disallow: /admin
Allow: /admin
"""
    parsed = CI.parse_robots(text)
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/admin') is True


def test_longer_disallow_beats_shorter_allow():
    text = """\
User-agent: *
Allow: /
Disallow: /admin/
"""
    parsed = CI.parse_robots(text)
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/admin/users') is False
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/products/') is True


def test_empty_disallow_is_a_noop():
    text = """\
User-agent: *
Disallow:
"""
    parsed = CI.parse_robots(text)
    assert CI.is_allowed(parsed, 'AcmeBot', 'https://x/anything') is True


# ----- Sanity checks -----------------------------------------------------


def test_catch_all_disallow_detected():
    text = "User-agent: *\nDisallow: /\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=False)
    assert any(f.check == 'catch_all_disallow' for f in findings)


def test_catch_all_disallow_opt_in_suppresses_finding():
    text = "User-agent: *\nDisallow: /\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=True)
    assert not any(f.check == 'catch_all_disallow' for f in findings)


def test_bom_detected_as_warning():
    text = "﻿User-agent: *\nDisallow: /admin/\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=False)
    assert any(f.severity == 'warning' and f.check == 'bom' for f in findings)


def test_crawl_delay_for_googlebot_warns():
    text = "User-agent: Googlebot\nCrawl-delay: 5\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=False)
    assert any(f.check == 'crawl_delay_for_googlebot' for f in findings)


def test_asset_block_warning_fires_on_static_path():
    text = "User-agent: Googlebot\nDisallow: /static/\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=False)
    assert any(f.check == 'asset_blocked' for f in findings)


def test_relative_sitemap_directive_is_error():
    text = "User-agent: *\nDisallow:\nSitemap: /sitemap.xml\n"
    parsed = CI.parse_robots(text)
    findings = CI.run_sanity_checks(parsed, text, allow_catch_all_disallow=False)
    assert any(
        f.check == 'sitemap_not_absolute' and f.severity == 'error'
        for f in findings
    )


# ----- Assertion suite integration ---------------------------------------


def test_shipping_assertion_suite_passes_against_shipping_robots():
    """
    The shipping tests/robots-tests.yaml describes the canonical
    chapter-15 robots.txt. Against a SHIPPING_ROBOTS fragment with the
    same coverage, every assertion should pass.
    """
    parsed = CI.parse_robots(SHIPPING_ROBOTS)
    tests = CI.load_tests(str(CHAPTER_DIR / 'tests' / 'robots-tests.yaml'))
    findings = CI.run_assertions(parsed, tests)
    assert findings == []


def test_assertion_failure_surfaces_as_error():
    parsed = CI.parse_robots("User-agent: *\nDisallow: /admin/\n")
    tests = {
        'allowed': [{'user_agent': 'Googlebot', 'url': 'https://x/admin/page'}],
        'blocked': [],
    }
    findings = CI.run_assertions(parsed, tests)
    assert len(findings) == 1
    assert findings[0].severity == 'error'
    assert findings[0].check == 'assertion_allowed'
