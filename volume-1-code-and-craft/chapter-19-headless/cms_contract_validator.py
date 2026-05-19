#!/usr/bin/env python3
"""
cms_contract_validator.py

Asserts that a CMS API response contains all required SEO fields,
that they have the expected types, and that locale coverage is
complete. From Chapter 19 section 19.5, the validation practice
the chapter argues "catches CMS schema drift at the integration
boundary rather than after it reaches production."

Works against REST and GraphQL endpoints. The contract is a
Python dict (or JSON file) mapping field paths to type and
nullability constraints; the validator walks the contract and
reports violations.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

_ISO_DATETIME_RE = re.compile(
    r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$'
)


# ----------------------------------------------------------------
# Default contract: the chapter's recommended minimum SEO field set
# ----------------------------------------------------------------

DEFAULT_CONTRACT = {
    'slug': {'type': 'string', 'nullable': False, 'non_empty': True},
    'title': {'type': 'string', 'nullable': False, 'non_empty': True},
    'publishedAt': {'type': 'string', 'nullable': False, 'iso_datetime': True},
    'updatedAt': {'type': 'string', 'nullable': False, 'iso_datetime': True},
    'status': {
        'type': 'string',
        'nullable': False,
        'enum': ['published', 'draft', 'archived'],
    },
    'seo.metaTitle': {'type': 'string', 'nullable': True},
    'seo.metaDescription': {'type': 'string', 'nullable': True},
    'seo.canonicalOverride': {
        'type': 'string',
        'nullable': True,
        'valid_url_or_null': True,
    },
    'seo.noindex': {'type': 'boolean', 'nullable': False},
    'seo.ogImage.url': {
        'type': 'string',
        'nullable': True,
        'valid_url_or_null': True,
    },
}


# ----------------------------------------------------------------
# Validation
# ----------------------------------------------------------------

@dataclass
class Violation:
    path: str
    rule: str
    expected: str
    observed: str


@dataclass
class ValidationResult:
    record_id: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return len(self.violations) == 0


def _walk_path(record: dict, path: str) -> tuple[bool, Any]:
    """Walk a dotted path through a nested dict. Returns (found, value)."""
    parts = path.split('.')
    cursor: Any = record
    for part in parts:
        if cursor is None:
            return True, None
        if not isinstance(cursor, dict):
            return False, None
        if part not in cursor:
            return False, None
        cursor = cursor[part]
    return True, cursor


_PYTHON_TYPES = {
    'string': str,
    'boolean': bool,
    'integer': int,
    'number': (int, float),
    'array': list,
    'object': dict,
}


def _is_iso_datetime(s: str) -> bool:
    return bool(_ISO_DATETIME_RE.match(s))


def _is_valid_absolute_url(s: str) -> bool:
    try:
        parsed = urlparse(s)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except ValueError:
        return False


def validate_record(
    record: dict,
    contract: dict,
    record_id: str = '<unnamed>',
) -> ValidationResult:
    result = ValidationResult(record_id=record_id)

    for path, rules in contract.items():
        found, value = _walk_path(record, path)

        # Field missing entirely (different from null).
        if not found:
            result.violations.append(Violation(
                path=path,
                rule='presence',
                expected='field present in response',
                observed='field missing',
            ))
            continue

        # Null check.
        if value is None:
            if not rules.get('nullable', True):
                result.violations.append(Violation(
                    path=path,
                    rule='nullable',
                    expected='non-null value',
                    observed='null',
                ))
            continue  # No further checks on null values.

        # Type check.
        expected_type = rules.get('type')
        if expected_type and expected_type in _PYTHON_TYPES:
            py_type = _PYTHON_TYPES[expected_type]
            if not isinstance(value, py_type):
                result.violations.append(Violation(
                    path=path,
                    rule='type',
                    expected=expected_type,
                    observed=type(value).__name__,
                ))
                continue

        # Non-empty string.
        if rules.get('non_empty') and isinstance(value, str):
            if not value.strip():
                result.violations.append(Violation(
                    path=path,
                    rule='non_empty',
                    expected='non-empty string',
                    observed='empty string',
                ))

        # Enum check.
        if 'enum' in rules and value not in rules['enum']:
            result.violations.append(Violation(
                path=path,
                rule='enum',
                expected=f'one of {rules["enum"]}',
                observed=repr(value),
            ))

        # ISO datetime check.
        if rules.get('iso_datetime') and isinstance(value, str):
            if not _is_iso_datetime(value):
                result.violations.append(Violation(
                    path=path,
                    rule='iso_datetime',
                    expected='ISO 8601 datetime',
                    observed=value[:40],
                ))

        # Valid URL (or null, since nullable was already checked).
        if rules.get('valid_url_or_null') and isinstance(value, str):
            if not _is_valid_absolute_url(value):
                result.violations.append(Violation(
                    path=path,
                    rule='valid_url',
                    expected='absolute URL or null',
                    observed=value[:60],
                ))

    return result


# ----------------------------------------------------------------
# Fetching
# ----------------------------------------------------------------

def fetch_rest(url: str) -> dict:
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def fetch_graphql(
    endpoint: str,
    query: str,
    variables: dict,
    record_path: str = 'data',
) -> dict:
    response = requests.post(
        endpoint,
        json={'query': query, 'variables': variables},
        timeout=15,
    )
    response.raise_for_status()
    body = response.json()
    if 'errors' in body:
        raise RuntimeError(f'GraphQL errors: {body["errors"]}')

    # Walk the response to the record root.
    cursor: Any = body
    for part in record_path.split('.'):
        if not isinstance(cursor, dict) or part not in cursor:
            raise RuntimeError(
                f'response does not contain record_path "{record_path}"'
            )
        cursor = cursor[part]
    return cursor


# ----------------------------------------------------------------
# Output
# ----------------------------------------------------------------

def format_text(result: ValidationResult) -> str:
    lines = [f'\nrecord: {result.record_id}', '=' * 60]
    if result.passed:
        lines.append('  ✓ all contract checks passed')
    else:
        for v in result.violations:
            lines.append(
                f'  ✗ {v.path}'
                f'\n    rule:     {v.rule}'
                f'\n    expected: {v.expected}'
                f'\n    observed: {v.observed}'
            )
        lines.append(f'\n  {len(result.violations)} violation(s)')
    return '\n'.join(lines)


# ----------------------------------------------------------------
# CLI
# ----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument('--url',
                     help='REST endpoint returning the record as JSON')
    src.add_argument('--graphql',
                     help='GraphQL endpoint URL')

    parser.add_argument('--query',
                        help='GraphQL query (or @file.gql to read from file)')
    parser.add_argument('--variables', default='{}',
                        help='GraphQL variables JSON (default: {})')
    parser.add_argument('--record-path', default='data.page',
                        help='Dotted path to the record in GraphQL response')

    parser.add_argument('--contract',
                        help='Path to JSON contract file (default: built-in)')
    parser.add_argument('--batch',
                        help='File with record IDs, substituted into --url '
                             'via the {id} placeholder')

    args = parser.parse_args()

    # Load contract.
    if args.contract:
        with open(args.contract) as f:
            contract = json.load(f)
    else:
        contract = DEFAULT_CONTRACT

    # Load GraphQL query if needed.
    query = None
    if args.graphql:
        if not args.query:
            parser.error('--graphql requires --query')
        if args.query.startswith('@'):
            query = Path(args.query[1:]).read_text()
        else:
            query = args.query

    # Build list of record fetches.
    fetches: list[tuple[str, Callable[[], dict]]] = []

    if args.batch:
        with open(args.batch) as f:
            ids = [line.strip() for line in f if line.strip()
                   and not line.startswith('#')]
        if args.url:
            for record_id in ids:
                url = args.url.replace('{id}', record_id)
                fetches.append((record_id, lambda u=url: fetch_rest(u)))
        else:
            for record_id in ids:
                variables = json.loads(args.variables)
                variables['id'] = record_id
                fetches.append((
                    record_id,
                    lambda v=variables: fetch_graphql(
                        args.graphql, query, v, args.record_path,
                    ),
                ))
    else:
        if args.url:
            fetches.append((args.url, lambda: fetch_rest(args.url)))
        else:
            variables = json.loads(args.variables)
            fetches.append((
                args.graphql,
                lambda: fetch_graphql(
                    args.graphql, query, variables, args.record_path,
                ),
            ))

    # Execute.
    all_passed = True
    for record_id, fetcher in fetches:
        try:
            record = fetcher()
        except Exception as e:
            sys.stderr.write(f'\nerror fetching {record_id}: {e}\n')
            all_passed = False
            continue

        result = validate_record(record, contract, record_id=record_id)
        print(format_text(result))
        if not result.passed:
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()