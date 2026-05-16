#!/usr/bin/env python3
"""
speculation-rules-validator.py

Validate a Speculation Rules JSON configuration against the risky
patterns described in Chapter 5 of SEO for Engineers, Volume 1.

The script can either fetch the rules from a live URL (parsing the
first <script type="speculationrules"> element in the response) or
read a local JSON file.

It flags:
  - eagerness: immediate paired with broad where patterns
  - eagerness: immediate paired with selector matches
  - missing eagerness, which defaults to immediate for `urls` lists
  - prerender rules pointing at URL patterns that look like one-time
    action pages (/checkout/, /confirm/, /unsubscribe/, /logout/,
    /order/*/complete, and similar)
  - cross-origin URLs in rules

Usage:
    python speculation-rules-validator.py --url https://example.com/
    python speculation-rules-validator.py --file rules.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 5.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 20

# Patterns that strongly suggest a URL performs an irreversible or
# side-effect-bearing action on load. Prerendering these is almost
# always wrong.
ONE_TIME_ACTION_PATTERNS = (
    r"/checkout(/|$)",
    r"/confirm(/|$)",
    r"/confirmation(/|$)",
    r"/order/[^/]+/complete",
    r"/order/[^/]+/confirmation",
    r"/payment(/|$)",
    r"/pay(/|$)",
    r"/unsubscribe(/|$)",
    r"/opt-out(/|$)",
    r"/logout(/|$)",
    r"/signout(/|$)",
    r"/sign-out(/|$)",
    r"/delete(/|$)",
    r"/cancel(/|$)",
    r"/verify(/|$)",
    r"/reset-password(/|$)",
    r"/password-reset(/|$)",
    r"/api(/|$)",
)

# Patterns considered "broad" when paired with eagerness: immediate.
# Anything that matches more than a single specific page falls in
# this bucket.
BROAD_PATTERN_INDICATORS = ("*", "/*", "{")


@dataclass
class Finding:
    """A single issue found during validation."""

    severity: str  # "high", "medium", "low"
    action: str    # "prerender" or "prefetch"
    rule_index: int
    message: str


@dataclass
class ValidationReport:
    """Aggregate validation output."""

    rules_action_counts: dict[str, int] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    page_origin: str | None = None

    @property
    def has_high_severity(self) -> bool:
        return any(f.severity == "high" for f in self.findings)


def fetch_rules_from_url(url: str) -> tuple[dict[str, Any], str]:
    """Fetch a URL and return the parsed speculation rules and origin."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    script = soup.find("script", attrs={"type": "speculationrules"})
    if not script or not script.string:
        raise ValueError(
            "no <script type=\"speculationrules\"> element found on the page"
        )

    parsed = json.loads(script.string)
    page_origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    return parsed, page_origin


def load_rules_from_file(path: Path) -> dict[str, Any]:
    """Read and parse a speculation rules JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def pattern_is_broad(pattern: str) -> bool:
    """Heuristic for whether a where pattern matches many URLs."""
    return any(token in pattern for token in BROAD_PATTERN_INDICATORS)


def is_one_time_action(target: str) -> bool:
    """Check whether a URL pattern looks like a one-time action page."""
    lower = target.lower()
    return any(re.search(p, lower) for p in ONE_TIME_ACTION_PATTERNS)


def collect_url_patterns(rule: dict[str, Any]) -> list[str]:
    """Collect the URL patterns or selectors a rule operates on."""
    patterns: list[str] = []
    if "urls" in rule and isinstance(rule["urls"], list):
        patterns.extend(str(u) for u in rule["urls"])
    where = rule.get("where")
    if isinstance(where, dict):
        patterns.extend(_extract_where_patterns(where))
    return patterns


def _extract_where_patterns(where: dict[str, Any]) -> list[str]:
    """Recursively extract pattern strings from a where clause."""
    out: list[str] = []
    if "href_matches" in where:
        value = where["href_matches"]
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, list):
            out.extend(str(v) for v in value)
    if "selector_matches" in where:
        value = where["selector_matches"]
        if isinstance(value, str):
            out.append("selector:" + value)
        elif isinstance(value, list):
            out.extend("selector:" + str(v) for v in value)
    for combinator in ("and", "or"):
        clauses = where.get(combinator)
        if isinstance(clauses, list):
            for clause in clauses:
                if isinstance(clause, dict):
                    out.extend(_extract_where_patterns(clause))
    not_clause = where.get("not")
    if isinstance(not_clause, dict):
        out.extend(_extract_where_patterns(not_clause))
    return out


def default_eagerness(rule: dict[str, Any]) -> str:
    """The default eagerness depends on how the rule selects URLs."""
    if "urls" in rule and isinstance(rule["urls"], list):
        return "immediate"
    return "conservative"


def validate(
    rules: dict[str, Any],
    page_origin: str | None = None,
) -> ValidationReport:
    """Validate a speculation rules document and return the report."""
    report = ValidationReport(page_origin=page_origin)

    for action in ("prerender", "prefetch"):
        rule_list = rules.get(action)
        if not isinstance(rule_list, list):
            continue
        report.rules_action_counts[action] = len(rule_list)
        for index, rule in enumerate(rule_list):
            _validate_rule(rule, action, index, report)

    return report


def _validate_rule(
    rule: dict[str, Any],
    action: str,
    index: int,
    report: ValidationReport,
) -> None:
    """Run the checks against a single rule and append findings."""
    eagerness = rule.get("eagerness")
    if eagerness is None:
        eagerness = default_eagerness(rule)
        if eagerness == "immediate":
            report.findings.append(
                Finding(
                    severity="medium",
                    action=action,
                    rule_index=index,
                    message=(
                        "no eagerness set, defaults to 'immediate' for "
                        "explicit urls lists. Set eagerness explicitly "
                        "to 'moderate' or 'conservative' if this is not "
                        "intended."
                    ),
                )
            )

    patterns = collect_url_patterns(rule)

    # Immediate + broad pattern is a high-severity finding for prerender,
    # medium for prefetch.
    if eagerness == "immediate":
        broad = [p for p in patterns if pattern_is_broad(p)]
        if broad:
            severity = "high" if action == "prerender" else "medium"
            report.findings.append(
                Finding(
                    severity=severity,
                    action=action,
                    rule_index=index,
                    message=(
                        f"eagerness: immediate paired with broad pattern(s) "
                        f"{broad}. Each user load will trigger speculative "
                        f"{action} for every matching URL. Switch to "
                        f"'moderate' or 'conservative' unless the resource "
                        f"cost is intended."
                    ),
                )
            )

    # Selector matches with prerender at immediate are almost never right.
    if action == "prerender" and eagerness == "immediate":
        selectors = [p for p in patterns if p.startswith("selector:")]
        if selectors:
            report.findings.append(
                Finding(
                    severity="high",
                    action=action,
                    rule_index=index,
                    message=(
                        f"prerender + eagerness: immediate + selector_matches "
                        f"({selectors}). Every link matching the selector "
                        f"will be prerendered on page load. Use 'moderate' "
                        f"or 'conservative' for selector-based prerender."
                    ),
                )
            )

    # One-time-action URLs should never be in any prerender rule.
    if action == "prerender":
        action_urls = [p for p in patterns if is_one_time_action(p)]
        if action_urls:
            report.findings.append(
                Finding(
                    severity="high",
                    action=action,
                    rule_index=index,
                    message=(
                        f"prerender targets URL pattern(s) that look like "
                        f"one-time-action pages: {action_urls}. Prerender "
                        f"will trigger any side effects on these pages "
                        f"speculatively. Exclude them from rules entirely."
                    ),
                )
            )

    # Cross-origin URLs need Supports-Loading-Mode consideration.
    if report.page_origin:
        cross_origin = []
        for p in patterns:
            if p.startswith("http://") or p.startswith("https://"):
                target_origin = (
                    f"{urlparse(p).scheme}://{urlparse(p).netloc}"
                )
                if target_origin and target_origin != report.page_origin:
                    cross_origin.append(p)
        if cross_origin:
            report.findings.append(
                Finding(
                    severity="medium",
                    action=action,
                    rule_index=index,
                    message=(
                        f"cross-origin target(s) {cross_origin}. Verify the "
                        f"target serves a Supports-Loading-Mode: "
                        f"credentialed-prerender response if authentication "
                        f"is required, or accept that cross-origin "
                        f"speculative requests are uncredentialed."
                    ),
                )
            )


def print_report(report: ValidationReport) -> None:
    """Print a human-readable summary."""
    print("Speculation rules validation report")
    print("=" * 40)
    if report.page_origin:
        print(f"page origin: {report.page_origin}")
    for action, count in report.rules_action_counts.items():
        print(f"{action} rules: {count}")
    print()

    if not report.findings:
        print("No issues found.")
        return

    by_severity: dict[str, list[Finding]] = {
        "high": [],
        "medium": [],
        "low": [],
    }
    for finding in report.findings:
        by_severity.setdefault(finding.severity, []).append(finding)

    for severity in ("high", "medium", "low"):
        findings = by_severity.get(severity, [])
        if not findings:
            continue
        print(f"{severity.upper()} severity ({len(findings)}):")
        for f in findings:
            print(f"  [{f.action} #{f.rule_index}] {f.message}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--url",
        help="Fetch and validate the first <script type='speculationrules'> "
        "found on this URL.",
    )
    source.add_argument(
        "--file",
        help="Read and validate a local JSON file containing speculation rules.",
    )
    args = parser.parse_args()

    try:
        if args.url:
            rules, origin = fetch_rules_from_url(args.url)
        else:
            rules = load_rules_from_file(Path(args.file))
            origin = None
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = validate(rules, page_origin=origin)
    print_report(report)

    # Exit non-zero on any high-severity finding, so the validator can
    # be wired into CI as a gate.
    return 0 if not report.has_high_severity else 1


if __name__ == "__main__":
    sys.exit(main())