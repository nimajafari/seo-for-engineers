#!/usr/bin/env python3
"""
headless_seo_audit.py

The Chapter 19 diagnostics checklist as a runnable script.
Fetches a URL with a configurable user agent and asserts the SEO
properties the chapter requires: status code, X-Robots-Tag,
non-empty body, head tags, JSON-LD validity, and OG metadata.

Exits 0 when all assertions pass, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_USER_AGENT = (
    'Mozilla/5.0 (compatible; HeadlessSeoAudit/1.0; '
    '+chapter-19-tooling)'
)
GOOGLEBOT_USER_AGENT = (
    'Mozilla/5.0 (compatible; Googlebot/2.1; '
    '+http://www.google.com/bot.html)'
)


@dataclass
class Assertion:
    name: str
    expected: str
    observed: str
    passed: bool


@dataclass
class AuditResult:
    url: str
    status_code: int
    assertions: list[Assertion] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(a.passed for a in self.assertions)


def audit_url(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    expect_status: int = 200,
    expect_redirect_to: str | None = None,
) -> AuditResult:
    session = requests.Session()
    session.headers.update({'User-Agent': user_agent})

    response = session.get(url, allow_redirects=False, timeout=15)
    result = AuditResult(url=url, status_code=response.status_code)

    # 1. Status code matches expectation.
    result.assertions.append(Assertion(
        name='status_code',
        expected=str(expect_status),
        observed=str(response.status_code),
        passed=response.status_code == expect_status,
    ))

    # If we expected a redirect, verify the Location header.
    if expect_redirect_to is not None:
        location = response.headers.get('Location', '')
        resolved = urljoin(url, location)
        result.assertions.append(Assertion(
            name='redirect_target',
            expected=expect_redirect_to,
            observed=resolved,
            passed=resolved.rstrip('/') == expect_redirect_to.rstrip('/'),
        ))
        return result

    # For non-200 expected (e.g. 404, 410), the remaining body
    # assertions don't apply.
    if expect_status != 200:
        return result

    # 2. X-Robots-Tag header: absent for indexable URLs.
    x_robots = response.headers.get('X-Robots-Tag', '')
    result.assertions.append(Assertion(
        name='x_robots_tag_not_noindex',
        expected='absent or no "noindex"',
        observed=x_robots or '(absent)',
        passed='noindex' not in x_robots.lower(),
    ))

    # 3. Response body is non-empty.
    body_len = len(response.text)
    result.assertions.append(Assertion(
        name='non_empty_body',
        expected='> 500 chars',
        observed=f'{body_len} chars',
        passed=body_len > 500,
    ))

    if body_len < 100:
        # Skip further parsing; the body is too small to be useful.
        return result

    soup = BeautifulSoup(response.text, 'html.parser')

    # 4. <title> tag present and non-empty.
    title_tag = soup.find('title')
    title_text = title_tag.text.strip() if title_tag else ''
    result.assertions.append(Assertion(
        name='title_tag',
        expected='non-empty <title>',
        observed=title_text[:60] if title_text else '(missing or empty)',
        passed=bool(title_text),
    ))

    # 5. <meta name="description"> present.
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    desc_content = (
        meta_desc.get('content', '').strip()
        if meta_desc else ''
    )
    result.assertions.append(Assertion(
        name='meta_description',
        expected='non-empty meta description',
        observed=desc_content[:60] if desc_content else '(missing or empty)',
        passed=bool(desc_content),
    ))

    # 6. <link rel="canonical"> present and valid absolute URL.
    canonical_tag = soup.find('link', rel='canonical')
    canonical_href = (
        canonical_tag.get('href', '').strip()
        if canonical_tag else ''
    )
    canonical_valid = _is_valid_absolute_url(canonical_href)
    result.assertions.append(Assertion(
        name='canonical_tag',
        expected='absolute URL in <link rel="canonical">',
        observed=canonical_href if canonical_href else '(missing)',
        passed=canonical_valid,
    ))

    # 7. At least one JSON-LD <script> block.
    jsonld_scripts = soup.find_all(
        'script', attrs={'type': 'application/ld+json'}
    )
    result.assertions.append(Assertion(
        name='jsonld_present',
        expected='at least one <script type="application/ld+json">',
        observed=f'{len(jsonld_scripts)} block(s)',
        passed=len(jsonld_scripts) > 0,
    ))

    # 8. All JSON-LD blocks parse as valid JSON.
    if jsonld_scripts:
        invalid_blocks = []
        for i, script in enumerate(jsonld_scripts):
            try:
                json.loads(script.string or '')
            except (json.JSONDecodeError, TypeError):
                invalid_blocks.append(i)
        result.assertions.append(Assertion(
            name='jsonld_parses',
            expected='all JSON-LD blocks valid JSON',
            observed=(
                'all valid'
                if not invalid_blocks
                else f'invalid blocks at index {invalid_blocks}'
            ),
            passed=not invalid_blocks,
        ))

    # 9, 10, 11. OG title, description, image.
    for og_field in ('og:title', 'og:description', 'og:image'):
        tag = soup.find('meta', attrs={'property': og_field})
        content = (
            tag.get('content', '').strip() if tag else ''
        )
        result.assertions.append(Assertion(
            name=f'meta_{og_field.replace(":", "_")}',
            expected=f'non-empty {og_field}',
            observed=content[:60] if content else '(missing)',
            passed=bool(content),
        ))

    return result


def _is_valid_absolute_url(s: str) -> bool:
    if not s:
        return False
    try:
        parsed = urlparse(s)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except ValueError:
        return False


def format_text(result: AuditResult) -> str:
    lines = [f'\n{result.url}', '=' * 80]
    for a in result.assertions:
        mark = '✓' if a.passed else '✗'
        lines.append(f'  {mark} {a.name:30s} {a.observed}')
    if result.passed:
        lines.append('\n  ALL ASSERTIONS PASSED')
    else:
        fail_count = sum(1 for a in result.assertions if not a.passed)
        lines.append(
            f'\n  {fail_count} of {len(result.assertions)} assertions FAILED'
        )
    return '\n'.join(lines)


def format_json(result: AuditResult) -> str:
    return json.dumps({
        'url': result.url,
        'status_code': result.status_code,
        'passed': result.passed,
        'assertions': [
            {
                'name': a.name,
                'expected': a.expected,
                'observed': a.observed,
                'passed': a.passed,
            }
            for a in result.assertions
        ],
    }, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('url', nargs='?',
                        help='URL to audit (omit with --batch)')
    parser.add_argument('--batch', action='store_true',
                        help='Read URLs from stdin, one per line')
    parser.add_argument('--user-agent', default=DEFAULT_USER_AGENT,
                        help='User-Agent header (default: HeadlessSeoAudit)')
    parser.add_argument('--googlebot', action='store_true',
                        help='Use the Googlebot user agent')
    parser.add_argument('--expect-404', action='store_true',
                        help='Assert URL returns 404 (for deleted content)')
    parser.add_argument('--expect-301',
                        help='Assert URL returns 301 redirecting to this URL')
    parser.add_argument('--base-url',
                        help='Prefix relative URLs with this base')
    parser.add_argument('--json', action='store_true',
                        help='Emit machine-readable JSON output')
    args = parser.parse_args()

    if args.googlebot:
        args.user_agent = GOOGLEBOT_USER_AGENT

    expect_status = 200
    expect_redirect_to = None
    if args.expect_404:
        expect_status = 404
    elif args.expect_301:
        expect_status = 301
        expect_redirect_to = args.expect_301

    urls: list[str] = []
    if args.batch:
        for line in sys.stdin:
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    elif args.url:
        urls.append(args.url)
    else:
        parser.error('provide a URL or use --batch')

    if args.base_url:
        urls = [
            u if u.startswith(('http://', 'https://')) else urljoin(args.base_url, u)
            for u in urls
        ]

    all_passed = True
    results = []
    for url in urls:
        try:
            result = audit_url(
                url,
                user_agent=args.user_agent,
                expect_status=expect_status,
                expect_redirect_to=expect_redirect_to,
            )
        except requests.RequestException as e:
            sys.stderr.write(f'\nerror fetching {url}: {e}\n')
            all_passed = False
            continue

        results.append(result)
        if not result.passed:
            all_passed = False

        if args.json:
            print(format_json(result))
        else:
            print(format_text(result))

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()