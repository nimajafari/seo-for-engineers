#!/usr/bin/env python3
"""
slug-generator-test-suite.py

Exercise a slug-generation function against the battery of edge
cases Chapter 12 of SEO for Engineers, Volume 1, identifies as
production failure points.

The suite imports a `generate_slug` function from a configurable
module and runs each test case against it. It reports pass/fail
per case and exits non-zero if any case fails.

Usage:
    # Test the example implementation in this directory
    python slug-generator-test-suite.py \\
      --module example_slug_implementation --function generate_slug

    # Test your own implementation
    python slug-generator-test-suite.py \\
      --module myapp.slugs --function make_slug

    # Run only specific categories
    python slug-generator-test-suite.py \\
      --module example_slug_implementation --function generate_slug \\
      --only diacritics,collisions,length

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import re
import sqlite3
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class TestCase:
    name: str
    category: str
    title: str
    expectations: list[Callable[[str], tuple[bool, str]]] = field(
        default_factory=list
    )


def expect_non_empty() -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        return (
            bool(slug),
            "slug was empty",
        )
    return check


def expect_only_ascii() -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = all(ord(c) < 128 for c in slug)
        return (
            ok,
            f"slug contains non-ASCII characters: {slug!r}",
        )
    return check


def expect_only_lowercase() -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = slug == slug.lower()
        return (
            ok,
            f"slug contains uppercase characters: {slug!r}",
        )
    return check


def expect_pattern(pattern: str) -> Callable[[str], tuple[bool, str]]:
    compiled = re.compile(pattern)
    def check(slug: str) -> tuple[bool, str]:
        ok = bool(compiled.match(slug))
        return (
            ok,
            f"slug {slug!r} does not match pattern {pattern!r}",
        )
    return check


def expect_max_length(length: int) -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = len(slug) <= length
        return (
            ok,
            f"slug length {len(slug)} exceeds max {length}",
        )
    return check


def expect_no_trailing_hyphen() -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = not (slug.startswith("-") or slug.endswith("-"))
        return (
            ok,
            f"slug has leading or trailing hyphen: {slug!r}",
        )
    return check


def expect_no_double_hyphen() -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = "--" not in slug
        return (
            ok,
            f"slug contains consecutive hyphens: {slug!r}",
        )
    return check


def expect_not_equal(forbidden: str) -> Callable[[str], tuple[bool, str]]:
    def check(slug: str) -> tuple[bool, str]:
        ok = slug != forbidden
        return (
            ok,
            f"slug must not equal {forbidden!r}, got {slug!r}",
        )
    return check


def basic_expectations(max_length: int = 80) -> list:
    return [
        expect_non_empty(),
        expect_only_ascii(),
        expect_only_lowercase(),
        expect_pattern(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$"),
        expect_max_length(max_length),
        expect_no_trailing_hyphen(),
        expect_no_double_hyphen(),
    ]


# Test cases organized by category. Each case provides a title and
# a list of expectations the resulting slug must satisfy.
TEST_CASES = [
    # Basic cases.
    TestCase(
        name="basic_lowercase_hyphens",
        category="basic",
        title="Hello World",
        expectations=basic_expectations() + [
            expect_pattern(r"^hello-world$"),
        ],
    ),
    TestCase(
        name="basic_already_lowercase",
        category="basic",
        title="already lowercase title",
        expectations=basic_expectations() + [
            expect_pattern(r"^already-lowercase-title$"),
        ],
    ),
    TestCase(
        name="basic_punctuation_stripped",
        category="basic",
        title="Hello, World! How are you?",
        expectations=basic_expectations(),
    ),

    # Diacritic stripping.
    TestCase(
        name="diacritics_latin_zurich",
        category="diacritics",
        title="Zürich",
        expectations=basic_expectations() + [
            expect_pattern(r"^zurich$"),
        ],
    ),
    TestCase(
        name="diacritics_latin_cafe",
        category="diacritics",
        title="A trip to the café",
        expectations=basic_expectations(),
    ),
    TestCase(
        name="diacritics_latin_naive",
        category="diacritics",
        title="A naïve approach",
        expectations=basic_expectations(),
    ),
    TestCase(
        name="diacritics_latin_sao_paulo",
        category="diacritics",
        title="São Paulo travel guide",
        expectations=basic_expectations(),
    ),

    # Non-Latin scripts. Either transliteration or a defined fallback
    # is acceptable, but the slug must not be empty.
    TestCase(
        name="non_latin_russian",
        category="non_latin",
        title="Москва",
        expectations=[
            expect_non_empty(),
            expect_only_ascii(),
            expect_only_lowercase(),
        ],
    ),
    TestCase(
        name="non_latin_japanese",
        category="non_latin",
        title="東京",
        expectations=[
            expect_non_empty(),
            expect_only_lowercase(),
        ],
    ),
    TestCase(
        name="non_latin_arabic",
        category="non_latin",
        title="مرحبا بالعالم",
        expectations=[
            expect_non_empty(),
            expect_only_lowercase(),
        ],
    ),
    TestCase(
        name="non_latin_greek",
        category="non_latin",
        title="Καλημέρα κόσμε",
        expectations=[
            expect_non_empty(),
            expect_only_lowercase(),
        ],
    ),

    # Reserved word protection.
    TestCase(
        name="reserved_admin",
        category="reserved",
        title="admin",
        expectations=basic_expectations() + [
            expect_not_equal("admin"),
        ],
    ),
    TestCase(
        name="reserved_login",
        category="reserved",
        title="login",
        expectations=basic_expectations() + [
            expect_not_equal("login"),
        ],
    ),
    TestCase(
        name="reserved_api",
        category="reserved",
        title="api",
        expectations=basic_expectations() + [
            expect_not_equal("api"),
        ],
    ),

    # Length truncation.
    TestCase(
        name="length_long_title",
        category="length",
        title=(
            "A very long article title that significantly exceeds the "
            "typical maximum slug length and must be truncated cleanly "
            "without breaking words in the middle of any term"
        ),
        expectations=basic_expectations(),
    ),

    # Empty and whitespace cases.
    TestCase(
        name="empty_string",
        category="empty",
        title="",
        expectations=[expect_non_empty()],
    ),
    TestCase(
        name="whitespace_only",
        category="empty",
        title="     ",
        expectations=[expect_non_empty()],
    ),
    TestCase(
        name="punctuation_only",
        category="empty",
        title="!!!???...",
        expectations=[expect_non_empty()],
    ),
]


def run_single_case(
    case: TestCase, generate_slug: Callable, max_length: int = 80
) -> tuple[bool, str, list[str]]:
    """Run one test case and return (passed, slug, failure_messages)."""
    try:
        slug = generate_slug(case.title, max_length=max_length)
    except TypeError:
        # Function may not accept max_length keyword.
        try:
            slug = generate_slug(case.title)
        except Exception as exc:
            return False, "", [f"function raised exception: {exc}"]
    except Exception as exc:
        return False, "", [f"function raised exception: {exc}"]

    failures: list[str] = []
    for expectation in case.expectations:
        ok, msg = expectation(slug)
        if not ok:
            failures.append(msg)
    return len(failures) == 0, slug, failures


def run_collision_case(generate_slug: Callable) -> tuple[bool, list[str]]:
    """Repeated generation against a tracked set must produce unique slugs."""
    existing: set[str] = set()

    def exists_fn(s: str) -> bool:
        return s in existing

    titles = [
        "Introduction to Python",
        "Introduction to Python",
        "Introduction to Python",
        "Introduction to Python",
    ]
    failures: list[str] = []
    produced = []

    sig = inspect.signature(generate_slug)
    if "exists_fn" not in sig.parameters:
        return False, [
            "function does not accept exists_fn parameter, "
            "cannot test collision resolution"
        ]

    for i, title in enumerate(titles):
        try:
            slug = generate_slug(title, exists_fn=exists_fn)
        except Exception as exc:
            failures.append(f"iteration {i} raised: {exc}")
            continue
        if slug in existing:
            failures.append(
                f"iteration {i} produced duplicate slug {slug!r}"
            )
        existing.add(slug)
        produced.append(slug)

    if len(set(produced)) != len(produced):
        failures.append(f"produced slugs not all unique: {produced}")

    return len(failures) == 0, failures


def run_race_condition_case(
    generate_slug: Callable,
) -> tuple[bool, list[str]]:
    """Simulate concurrent insertions against a SQLite unique constraint."""
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute(
        "CREATE TABLE articles (slug TEXT PRIMARY KEY, title TEXT)"
    )
    db.commit()

    lock = threading.Lock()

    def exists_fn(s: str) -> bool:
        cur = db.execute("SELECT 1 FROM articles WHERE slug = ?", (s,))
        return cur.fetchone() is not None

    results: list[tuple[bool, str]] = []
    failures: list[str] = []

    def worker(title: str) -> None:
        sig = inspect.signature(generate_slug)
        try:
            if "exists_fn" in sig.parameters:
                slug = generate_slug(title, exists_fn=exists_fn)
            else:
                slug = generate_slug(title)
            with lock:
                try:
                    db.execute(
                        "INSERT INTO articles (slug, title) VALUES (?, ?)",
                        (slug, title),
                    )
                    db.commit()
                    results.append((True, slug))
                except sqlite3.IntegrityError:
                    # Race condition fired. Retry with collision
                    # resolution against the now-populated table.
                    if "exists_fn" in sig.parameters:
                        slug = generate_slug(title, exists_fn=exists_fn)
                        try:
                            db.execute(
                                "INSERT INTO articles "
                                "(slug, title) VALUES (?, ?)",
                                (slug, title),
                            )
                            db.commit()
                            results.append((True, slug))
                        except sqlite3.IntegrityError as exc:
                            results.append((False, str(exc)))
                    else:
                        results.append((False, "no exists_fn"))
        except Exception as exc:
            results.append((False, f"exception: {exc}"))

    title = "Concurrent Title Test"
    threads = [
        threading.Thread(target=worker, args=(title,))
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    db.close()

    successes = [s for ok, s in results if ok]
    if len(successes) != 5:
        failures.append(
            f"expected 5 successful inserts, got {len(successes)}, "
            f"results: {results}"
        )
    if len(set(successes)) != len(successes):
        failures.append(
            f"concurrent inserts produced duplicate slugs: {successes}"
        )

    return len(failures) == 0, failures


def load_generate_slug(module_name: str, function_name: str) -> Callable:
    """Import and return the generate_slug function under test."""
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(
            f"FATAL: could not import module {module_name}: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    if not hasattr(module, function_name):
        print(
            f"FATAL: module {module_name} has no attribute "
            f"{function_name}",
            file=sys.stderr,
        )
        sys.exit(2)

    return getattr(module, function_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--module",
        default="example_slug_implementation",
        help=(
            "Python module containing the slug function. Default, "
            "example_slug_implementation."
        ),
    )
    parser.add_argument(
        "--function",
        default="generate_slug",
        help="Name of the function in the module. Default, generate_slug.",
    )
    parser.add_argument(
        "--only",
        help=(
            "Comma-separated list of categories to run, e.g. "
            "basic,diacritics,collisions. Default runs all."
        ),
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=80,
        help="Max length passed to the slug function. Default, 80.",
    )
    args = parser.parse_args()

    # Ensure the script's own directory is on the import path so
    # the default example_slug_implementation module resolves.
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

    generate_slug = load_generate_slug(args.module, args.function)

    categories = (
        set(c.strip() for c in args.only.split(","))
        if args.only
        else None
    )

    results: list[dict[str, Any]] = []

    # Standard cases.
    for case in TEST_CASES:
        if categories and case.category not in categories:
            continue
        ok, slug, failures = run_single_case(
            case, generate_slug, max_length=args.max_length
        )
        results.append({
            "name": case.name,
            "category": case.category,
            "passed": ok,
            "slug": slug,
            "failures": failures,
        })

    # Collision case.
    if not categories or "collisions" in categories:
        ok, failures = run_collision_case(generate_slug)
        results.append({
            "name": "collisions_sequential",
            "category": "collisions",
            "passed": ok,
            "slug": "",
            "failures": failures,
        })

    # Race condition case.
    if not categories or "race" in categories:
        ok, failures = run_race_condition_case(generate_slug)
        results.append({
            "name": "race_condition_concurrent_insert",
            "category": "race",
            "passed": ok,
            "slug": "",
            "failures": failures,
        })

    # Report.
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])

    print(f"\nSlug generator test suite", file=sys.stderr)
    print(f"Module, {args.module}.{args.function}", file=sys.stderr)
    print(
        f"Results, {passed} passed, {failed} failed "
        f"({len(results)} total)\n",
        file=sys.stderr,
    )

    for r in results:
        marker = "PASS" if r["passed"] else "FAIL"
        slug_part = f" -> {r['slug']!r}" if r["slug"] else ""
        print(
            f"  {marker}  [{r['category']:<12}] {r['name']}{slug_part}",
            file=sys.stderr,
        )
        for failure in r["failures"]:
            print(f"         {failure}", file=sys.stderr)

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())