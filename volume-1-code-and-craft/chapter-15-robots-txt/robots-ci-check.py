#!/usr/bin/env python3
"""
robots-ci-check.py

Validate a robots.txt file against an explicit assertion suite,
using a Python port of Google's parsing rules.

Implements:
  - Group selection by most specific User-agent (with same-token merge).
  - Rule precedence by literal character count, Allow breaks ties.
  - Wildcard semantics: * (zero or more), $ (end anchor).
  - Sanity checks: BOM, catch-all Disallow, asset path blocking,
    Crawl-delay for Googlebot, malformed Sitemap directives.

Exits non-zero on error-severity findings. Pass --strict to promote
warnings to errors.
"""

import argparse
import json
import re
import sys
import urllib.parse
from dataclasses import asdict, dataclass, field

import requests
import yaml

USER_AGENT = 'RobotsCICheck/1.0 (+chapter-15-tooling)'
DEFAULT_TIMEOUT = 15

ASSET_BLOCK_WARNINGS = (
    re.compile(r'\.css\$?$'),
    re.compile(r'\.js\$?$'),
    re.compile(r'^/static/?$'),
    re.compile(r'^/assets/?$'),
    re.compile(r'^/_next/?$'),
    re.compile(r'^/_nuxt/?$'),
    re.compile(r'^/build/?$'),
)


@dataclass
class Rule:
    directive: str
    path: str

    @property
    def literal_length(self):
        return sum(1 for c in self.path if c not in ('*', '$'))


@dataclass
class Group:
    user_agents: list
    rules: list = field(default_factory=list)


@dataclass
class ParsedRobots:
    groups: list = field(default_factory=list)
    sitemaps: list = field(default_factory=list)
    raw_lines: list = field(default_factory=list)


@dataclass
class Finding:
    severity: str
    check: str
    detail: str
    line: int | None = None


def parse_robots(text):
    parsed = ParsedRobots()
    parsed.raw_lines = text.splitlines()
    current_group = None
    expecting_user_agent = True
    for lineno, raw in enumerate(parsed.raw_lines, start=1):
        line = raw.split('#', 1)[0].strip()
        if not line:
            expecting_user_agent = True
            continue
        if ':' not in line:
            continue
        directive, _, value = line.partition(':')
        directive = directive.strip().lower()
        value = value.strip()

        if directive == 'sitemap':
            parsed.sitemaps.append((value, lineno))
            continue

        if directive == 'user-agent':
            if expecting_user_agent or current_group is None:
                current_group = Group(user_agents=[value])
                parsed.groups.append(current_group)
                expecting_user_agent = False
            else:
                current_group.user_agents.append(value)
            continue

        if directive in ('allow', 'disallow') and current_group is not None:
            current_group.rules.append(Rule(directive=directive, path=value))
            expecting_user_agent = False
            continue

        if directive == 'crawl-delay' and current_group is not None:
            current_group.rules.append(Rule(directive='crawl-delay', path=value))
            expecting_user_agent = False
            continue

    return parsed


def select_group_for_user_agent(parsed, user_agent):
    ua_lower = user_agent.lower()
    best_token = None
    best_specificity = -1
    has_fallback = False
    for group in parsed.groups:
        for token in group.user_agents:
            token_lower = token.lower()
            if token_lower == '*':
                has_fallback = True
                continue
            if token_lower in ua_lower:
                if len(token_lower) > best_specificity:
                    best_specificity = len(token_lower)
                    best_token = token_lower

    if best_token is not None:
        merged_rules = []
        for group in parsed.groups:
            if any(t.lower() == best_token for t in group.user_agents):
                merged_rules.extend(group.rules)
        return Group(user_agents=[best_token], rules=merged_rules)

    if has_fallback:
        merged_rules = []
        for group in parsed.groups:
            if any(t.strip() == '*' for t in group.user_agents):
                merged_rules.extend(group.rules)
        return Group(user_agents=['*'], rules=merged_rules)

    return None


def path_matches(pattern, url_path):
    regex_parts = []
    for ch in pattern:
        if ch == '*':
            regex_parts.append('.*')
        elif ch == '$':
            regex_parts.append('$')
        else:
            regex_parts.append(re.escape(ch))
    regex = '^' + ''.join(regex_parts)
    return re.match(regex, url_path) is not None


def is_allowed(parsed, user_agent, url):
    group = select_group_for_user_agent(parsed, user_agent)
    if group is None:
        return True

    parsed_url = urllib.parse.urlsplit(url)
    url_path = parsed_url.path
    if parsed_url.query:
        url_path += '?' + parsed_url.query

    matching = [r for r in group.rules
                if r.directive in ('allow', 'disallow')
                and r.path
                and path_matches(r.path, url_path)]

    if not matching:
        return True

    max_len = max(r.literal_length for r in matching)
    top = [r for r in matching if r.literal_length == max_len]
    if any(r.directive == 'allow' for r in top):
        return True
    return False


def run_sanity_checks(parsed, raw_text, allow_catch_all_disallow):
    findings = []

    if raw_text.startswith('\ufeff'):
        findings.append(Finding(
            severity='warning',
            check='bom',
            detail='UTF-8 BOM detected at start of file. Some parsers '
                   'do not tolerate this. Configure your file handler '
                   'to strip BOMs.',
            line=1,
        ))

    for group in parsed.groups:
        is_catch_all_group = any(t.strip() == '*' for t in group.user_agents)
        for rule in group.rules:
            if (is_catch_all_group
                    and rule.directive == 'disallow'
                    and rule.path == '/'
                    and not allow_catch_all_disallow):
                findings.append(Finding(
                    severity='error',
                    check='catch_all_disallow',
                    detail='User-agent: * with Disallow: / blocks every '
                           'compliant crawler from the entire site. If '
                           'this is intentional (e.g. for staging), '
                           'pass --allow-catch-all-disallow.',
                ))

    for group in parsed.groups:
        targets_googlebot = any(
            'googlebot' in t.lower() for t in group.user_agents
        )
        for rule in group.rules:
            if rule.directive == 'crawl-delay' and targets_googlebot:
                findings.append(Finding(
                    severity='warning',
                    check='crawl_delay_for_googlebot',
                    detail=f'Crawl-delay: {rule.path} is set for a '
                           'Googlebot user-agent token. Google does not '
                           'honor Crawl-delay; manage crawl rate via '
                           'Search Console instead.',
                ))

    for group in parsed.groups:
        if not any('googlebot' in t.lower() or t.strip() == '*'
                   for t in group.user_agents):
            continue
        for rule in group.rules:
            if rule.directive != 'disallow':
                continue
            for pattern in ASSET_BLOCK_WARNINGS:
                if pattern.search(rule.path):
                    findings.append(Finding(
                        severity='warning',
                        check='asset_blocked',
                        detail=f'Disallow: {rule.path} (for '
                               f'{", ".join(group.user_agents)}) may '
                               'block CSS, JavaScript, or framework '
                               'assets that Googlebot needs to render '
                               'the page. Verify against the rendering '
                               'requirements in Chapter 5.',
                    ))
                    break

    for sitemap, lineno in parsed.sitemaps:
        if not sitemap.startswith(('http://', 'https://')):
            findings.append(Finding(
                severity='error',
                check='sitemap_not_absolute',
                detail=f'Sitemap: {sitemap} is not an absolute URL. '
                       'The Sitemap directive requires an absolute URL.',
                line=lineno,
            ))

    return findings


def run_assertions(parsed, tests):
    findings = []
    for entry in tests.get('allowed', []):
        ua = entry['user_agent']
        url = entry['url']
        if not is_allowed(parsed, ua, url):
            findings.append(Finding(
                severity='error',
                check='assertion_allowed',
                detail=f'{ua} should be ALLOWED to fetch {url} '
                       'but the file blocks it.',
            ))
    for entry in tests.get('blocked', []):
        ua = entry['user_agent']
        url = entry['url']
        if is_allowed(parsed, ua, url):
            findings.append(Finding(
                severity='error',
                check='assertion_blocked',
                detail=f'{ua} should be BLOCKED from {url} '
                       'but the file allows it.',
            ))
    return findings


def load_robots(args):
    if args.robots:
        with open(args.robots, encoding='utf-8') as f:
            return f.read()
    if args.robots_url:
        resp = requests.get(
            args.robots_url,
            headers={'User-Agent': USER_AGENT},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.text
    raise ValueError('one of --robots or --robots-url is required')


def load_tests(path):
    if path is None:
        return None
    with open(path, encoding='utf-8') as f:
        text = f.read()
    if path.endswith('.json'):
        return json.loads(text)
    return yaml.safe_load(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--robots', help='Local robots.txt file path')
    source.add_argument('--robots-url', help='Live robots.txt URL')
    parser.add_argument('--tests', help='YAML or JSON assertion suite')
    parser.add_argument(
        '--strict', action='store_true',
        help='Promote warnings to errors',
    )
    parser.add_argument(
        '--allow-catch-all-disallow', action='store_true',
        help='Skip the catch-all Disallow: / check (use on staging)',
    )
    parser.add_argument('--output', help='Write JSON report to this file')
    args = parser.parse_args()

    raw_text = load_robots(args)
    parsed = parse_robots(raw_text)

    findings = run_sanity_checks(parsed, raw_text, args.allow_catch_all_disallow)
    if args.tests:
        tests = load_tests(args.tests)
        findings.extend(run_assertions(parsed, tests))

    if args.strict:
        findings = [
            Finding(severity='error', check=f.check, detail=f.detail, line=f.line)
            if f.severity == 'warning' else f
            for f in findings
        ]

    report = {'findings': [asdict(f) for f in findings]}
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
    else:
        json.dump(report, sys.stdout, indent=2)
        print()

    has_errors = any(f.severity == 'error' for f in findings)
    sys.exit(1 if has_errors else 0)


if __name__ == '__main__':
    main()