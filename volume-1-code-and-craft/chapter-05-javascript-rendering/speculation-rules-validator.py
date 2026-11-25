#!/usr/bin/env python3
"""
speculation-rules-validator.py

Validate a Speculation Rules JSON configuration against the risky
patterns described in Chapter 5 of SEO for Engineers, Volume 1.

The script can either fetch the rules from a live URL or read a local
JSON file. For a URL it collects every source the browser would use:
all <script type="speculationrules"> elements and every JSON file named
in a Speculation-Rules response header (CDN features such as
Cloudflare's Speed Brain deliver rules that way), and merges them.

Patterns under a "not" clause are exclusions, not targets: a rule that
prerenders "/*" except "/logout" is the safe, recommended shape and is
not flagged for /logout.

It flags:
  - eagerness: immediate paired with broad where patterns
  - eagerness: immediate paired with selector matches
  - an invalid eagerness value, which makes the browser ignore the rule
  - missing eagerness, which defaults to immediate for `urls` lists
  - prerender rules targeting URL patterns that look like one-time
    action pages (/checkout/, /confirm/, /unsubscribe/, /logout/,
    /order/*/complete, and similar)
  - broad prerender rules with no exclusions at all (low severity)
  - cross-origin URLs in rules
  - rule sources the browser would ignore (invalid JSON, unfetchable
    Speculation-Rules header files)

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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# The eagerness values defined by the Speculation Rules spec. Any other
# value is invalid and causes the browser to ignore the rule.
VALID_EAGERNESS = ("immediate", "eager", "moderate", "conservative")

# Patterns that strongly suggest a URL performs an irreversible or
# side-effect-bearing action on load. Prerendering these is almost
# always wrong. The (/|\?|$) boundary stops a segment at a slash, a
# query string, or the end of the URL, so /checkout?step=1 is caught.
_END = r"(/|\?|$)"
ONE_TIME_ACTION_PATTERNS = (
    rf"/checkout{_END}",
    rf"/confirm{_END}",
    rf"/confirmation{_END}",
    rf"/order/[^/]+/complete{_END}",
    rf"/order/[^/]+/confirmation{_END}",
    rf"/payment{_END}",
    rf"/pay{_END}",
    rf"/cart{_END}",
    rf"/add-to-cart{_END}",
    r"[?&]add[-_]to[-_]cart=",
    rf"/unsubscribe{_END}",
    rf"/opt-out{_END}",
    rf"/logout{_END}",
    rf"/signout{_END}",
    rf"/sign-out{_END}",
    rf"/delete{_END}",
    rf"/cancel{_END}",
    rf"/verify{_END}",
    rf"/reset-password{_END}",
    rf"/password-reset{_END}",
    rf"/api{_END}",
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
    # Problems with the rule sources themselves (a script that is not
    # valid JSON, a header file that could not be fetched). The browser
    # skips such a source, so its speculation silently never happens.
    source_problems: list[str] = field(default_factory=list)

    @property
    def has_high_severity(self) -> bool:
        return any(f.severity == "high" for f in self.findings)


def merge_rule_document(merged: dict[str, list], parsed: Any) -> None:
    """Append a parsed rules document's prerender/prefetch lists to merged."""
    if not isinstance(parsed, dict):
        raise ValueError("top level is not a JSON object")
    for action in ("prerender", "prefetch"):
        rule_list = parsed.get(action)
        if isinstance(rule_list, list):
            merged[action].extend(rule_list)


def header_rule_urls(header_value: str | None, page_url: str) -> list[str]:
    """Return the JSON URLs named in a Speculation-Rules response header.

    The header is a structured-field list of quoted URL strings, resolved
    relative to the document URL.
    """
    if not header_value:
        return []
    return [urljoin(page_url, u) for u in re.findall(r'"([^"]*)"', header_value)]


def fetch_rules_from_url(url: str) -> tuple[dict[str, Any], str, list[str]]:
    """Fetch a URL and return (merged rules, page origin, source problems).

    The browser unions every <script type="speculationrules"> element and
    every rules file named in the Speculation-Rules response header, so
    the validator merges all of them. A source that does not parse is
    skipped by the browser rather than fatal, so it is reported as a
    source problem while the remaining sources are still validated.
    """
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    page_url = response.url

    merged: dict[str, Any] = {"prerender": [], "prefetch": []}
    problems: list[str] = []
    sources = 0

    soup = BeautifulSoup(response.content, "html.parser")
    for i, script in enumerate(
        soup.find_all("script", attrs={"type": "speculationrules"}), start=1
    ):
        sources += 1
        try:
            merge_rule_document(merged, json.loads(script.get_text()))
        except (ValueError, TypeError) as exc:
            problems.append(f"<script type=speculationrules> #{i} is ignored: {exc}")

    for rules_url in header_rule_urls(response.headers.get("Speculation-Rules"), page_url):
        sources += 1
        try:
            rules_response = requests.get(
                rules_url,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
            rules_response.raise_for_status()
            merge_rule_document(merged, rules_response.json())
        except (requests.RequestException, ValueError, TypeError) as exc:
            problems.append(f"Speculation-Rules header file {rules_url} is ignored: {exc}")

    if not sources:
        raise ValueError(
            "no <script type=\"speculationrules\"> element and no "
            "Speculation-Rules header found"
        )

    # Drop empty action buckets so the report only counts what is present.
    merged = {action: rules for action, rules in merged.items() if rules}
    if not merged and not problems:
        raise ValueError(
            "speculation rules source(s) present but contained no "
            "prerender or prefetch rules"
        )

    parsed_page = urlparse(page_url)
    page_origin = f"{parsed_page.scheme}://{parsed_page.netloc}"
    return merged, page_origin, problems


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
    """Collect the URL patterns or selectors a rule targets.

    Patterns under a "not" clause are exclusions and are not returned;
    see collect_excluded_patterns.
    """
    return _collect(rule)[0]


def collect_excluded_patterns(rule: dict[str, Any]) -> list[str]:
    """Collect the patterns a rule excludes via "not" clauses."""
    return _collect(rule)[1]


def _collect(rule: dict[str, Any]) -> tuple[list[str], list[str]]:
    targets: list[str] = []
    excluded: list[str] = []
    if "urls" in rule and isinstance(rule["urls"], list):
        targets.extend(str(u) for u in rule["urls"])
    where = rule.get("where")
    if isinstance(where, dict):
        _extract_where_patterns(where, targets, excluded)
    return targets, excluded


def _url_pattern_to_string(value: Any) -> str:
    """Render an href_matches value (string or URLPattern object) as text.

    href_matches also accepts a URLPattern init object such as
    {"pathname": "/product/*"}; without this, object patterns were
    silently skipped by every check.
    """
    if not isinstance(value, dict):
        return str(value)
    origin = ""
    if value.get("hostname"):
        scheme = str(value.get("protocol", "https")).rstrip(":")
        port = f":{value['port']}" if value.get("port") else ""
        origin = f"{scheme}://{value['hostname']}{port}"
    path = str(value.get("pathname", "/*" if origin else "*"))
    search = f"?{str(value['search']).lstrip('?')}" if value.get("search") else ""
    return f"{origin}{path}{search}"


def _extract_where_patterns(
    where: dict[str, Any],
    targets: list[str],
    excluded: list[str],
    negated: bool = False,
) -> None:
    """Walk a where clause, sorting patterns by polarity.

    Each "not" flips polarity, so not(not(x)) is a target again.
    """
    bucket = excluded if negated else targets
    if "href_matches" in where:
        value = where["href_matches"]
        values = value if isinstance(value, list) else [value]
        bucket.extend(_url_pattern_to_string(v) for v in values)
    if "selector_matches" in where:
        value = where["selector_matches"]
        values = value if isinstance(value, list) else [value]
        bucket.extend("selector:" + str(v) for v in values)
    for combinator in ("and", "or"):
        clauses = where.get(combinator)
        if isinstance(clauses, list):
            for clause in clauses:
                if isinstance(clause, dict):
                    _extract_where_patterns(clause, targets, excluded, negated)
    not_clause = where.get("not")
    if isinstance(not_clause, dict):
        _extract_where_patterns(not_clause, targets, excluded, not negated)


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

    # An explicit but invalid eagerness value makes the browser ignore the
    # rule outright, so the speculation silently never happens.
    if eagerness is not None and eagerness not in VALID_EAGERNESS:
        report.findings.append(
            Finding(
                severity="medium",
                action=action,
                rule_index=index,
                message=(
                    f"eagerness '{eagerness}' is not a valid value. Use one "
                    f"of {', '.join(VALID_EAGERNESS)}. The browser ignores a "
                    f"rule with an invalid eagerness, so this speculation "
                    f"never runs."
                ),
            )
        )

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

    # A broad prerender rule with no exclusions will also prerender any
    # matching link to an action page that appears on the page later.
    if action == "prerender" and not collect_excluded_patterns(rule):
        broad_targets = [
            p for p in patterns if not p.startswith("selector:") and pattern_is_broad(p)
        ]
        if broad_targets:
            report.findings.append(
                Finding(
                    severity="low",
                    action=action,
                    rule_index=index,
                    message=(
                        f"broad prerender pattern(s) {broad_targets} with no "
                        f"exclusions. Add \"not\" clauses for action URLs "
                        f"(logout, add-to-cart, unsubscribe) so links to them "
                        f"are never prerendered."
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

    if report.source_problems:
        print(f"IGNORED rule sources ({len(report.source_problems)}):")
        for problem in report.source_problems:
            print(f"  {problem}")
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
        help="Fetch this URL and validate every <script type='speculationrules'> "
        "and Speculation-Rules header file on it.",
    )
    source.add_argument(
        "--file",
        help="Read and validate a local JSON file containing speculation rules.",
    )
    args = parser.parse_args()

    problems: list[str] = []
    try:
        if args.url:
            rules, origin, problems = fetch_rules_from_url(args.url)
        else:
            rules = load_rules_from_file(Path(args.file))
            origin = None
            if not isinstance(rules, dict):
                raise ValueError("top level of the rules file is not a JSON object")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = validate(rules, page_origin=origin)
    report.source_problems = problems
    print_report(report)

    # Exit non-zero on any high-severity finding, so the validator can
    # be wired into CI as a gate.
    return 0 if not report.has_high_severity else 1


if __name__ == "__main__":
    sys.exit(main())