#!/usr/bin/env python3
"""
robots-post-deploy-smoke.py

Fetch the live robots.txt from a production origin after deploy and
verify that what is being served matches what was expected. Intended
to run as the final step of a deployment pipeline.

Implements:
  - Reachability (HTTP 200 with a body).
  - Correct Content-Type (text/plain).
  - No redirect chain on the canonical host.
  - No catch-all Disallow: / for Googlebot.
  - Optional content hash match against the build artifact.
  - Optional URL allow/block assertion suite.
  - Optional verification that alternative hosts redirect to the
    canonical robots.txt.

Exits non-zero on any error-severity finding.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass

import requests

import importlib.util
import os

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    'robots_ci_check', os.path.join(THIS_DIR, 'robots-ci-check.py')
)
CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CI)

USER_AGENT = 'RobotsPostDeploySmoke/1.0 (+chapter-15-tooling)'
DEFAULT_TIMEOUT = 15


@dataclass
class Finding:
    severity: str
    check: str
    detail: str


def fetch(url, allow_redirects=False):
    return requests.get(
        url,
        headers={'User-Agent': USER_AGENT},
        timeout=DEFAULT_TIMEOUT,
        allow_redirects=allow_redirects,
    )


def check_canonical_host(url):
    findings = []
    try:
        resp = fetch(url, allow_redirects=False)
    except requests.RequestException as e:
        findings.append(Finding(
            severity='error',
            check='reachability',
            detail=f'fetch failed: {e}',
        ))
        return findings, None, None

    if 300 <= resp.status_code < 400:
        findings.append(Finding(
            severity='error',
            check='canonical_redirect',
            detail=f'canonical robots.txt URL returned {resp.status_code}; '
                   'the canonical host should serve the file directly',
        ))
        return findings, None, None

    if resp.status_code != 200:
        findings.append(Finding(
            severity='error',
            check='status',
            detail=f'expected 200, got {resp.status_code}',
        ))
        return findings, None, None

    content_type = (resp.headers.get('Content-Type') or '').lower()
    if 'text/plain' not in content_type:
        findings.append(Finding(
            severity='warning',
            check='content_type',
            detail=f'expected text/plain, got {content_type or "no Content-Type"}',
        ))

    return findings, resp.text, resp.content


def check_googlebot_not_blocked(parsed_robots, origin):
    findings = []
    test_url = origin.rstrip('/') + '/'
    if not CI.is_allowed(parsed_robots, 'Googlebot', test_url):
        findings.append(Finding(
            severity='error',
            check='googlebot_blocked',
            detail=f'live robots.txt blocks Googlebot from {test_url}. '
                   'This is the catch-all-Disallow failure pattern.',
        ))
    return findings


def check_hash(raw_bytes, expected_hash):
    findings = []
    actual = hashlib.sha256(raw_bytes).hexdigest()
    if actual != expected_hash:
        findings.append(Finding(
            severity='error',
            check='hash_mismatch',
            detail=f'expected SHA-256 {expected_hash}, got {actual}',
        ))
    return findings


def check_assertion_suite(parsed_robots, tests):
    findings = []
    ci_findings = CI.run_assertions(parsed_robots, tests)
    for f in ci_findings:
        findings.append(Finding(
            severity=f.severity, check=f.check, detail=f.detail,
        ))
    return findings


def check_alternative_host(url, canonical_url):
    findings = []
    try:
        resp = fetch(url, allow_redirects=False)
    except requests.RequestException as e:
        findings.append(Finding(
            severity='warning',
            check='alt_host_fetch',
            detail=f'{url} fetch failed: {e}',
        ))
        return findings

    if resp.status_code == 200:
        return findings

    if 300 <= resp.status_code < 400:
        location = resp.headers.get('Location', '')
        if location == canonical_url or location.endswith('/robots.txt'):
            return findings
        findings.append(Finding(
            severity='warning',
            check='alt_host_redirect',
            detail=f'{url} redirects to {location}, not to '
                   f'{canonical_url}',
        ))
        return findings

    findings.append(Finding(
        severity='error',
        check='alt_host_status',
        detail=f'{url} returned {resp.status_code}; expected 200 or 3xx',
    ))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--robots-url', required=True,
        help='The canonical production robots.txt URL',
    )
    parser.add_argument(
        '--expected-hash',
        help='SHA-256 hash of the expected file body (hex)',
    )
    parser.add_argument(
        '--tests',
        help='YAML or JSON assertion suite (same format as robots-ci-check.py)',
    )
    parser.add_argument(
        '--also-check', action='append', default=[],
        help='Alternative robots.txt URLs to verify (apex, http variant, etc.)',
    )
    parser.add_argument('--output', help='Write JSON report to this file')
    args = parser.parse_args()

    findings = []
    canonical_findings, body, raw_bytes = check_canonical_host(args.robots_url)
    findings.extend(canonical_findings)

    if body is not None:
        parsed = CI.parse_robots(body)
        origin = '/'.join(args.robots_url.split('/')[:3])
        findings.extend(check_googlebot_not_blocked(parsed, origin))

        if args.expected_hash:
            findings.extend(check_hash(raw_bytes, args.expected_hash))

        if args.tests:
            tests = CI.load_tests(args.tests)
            findings.extend(check_assertion_suite(parsed, tests))

    for alt_url in args.also_check:
        findings.extend(check_alternative_host(alt_url, args.robots_url))

    report = {
        'robots_url': args.robots_url,
        'findings': [asdict(f) for f in findings],
    }
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