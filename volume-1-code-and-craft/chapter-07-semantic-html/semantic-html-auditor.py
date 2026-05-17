#!/usr/bin/env python3
"""
semantic-html-auditor.py

Audit a URL (or a list of URLs) for the semantic HTML patterns that
Chapter 7 of SEO for Engineers, Volume 1, identifies as having the
highest SEO impact.

The audit reports findings in three severity buckets. High severity
findings include missing or duplicated h1, missing or duplicated main,
anchor elements without href, and anchor elements that produce no
text signal at all. Medium severity findings include skipped heading
levels, missing alt attributes on images, and generic template-level
alt text. Low severity findings include missing landmark elements and
headings inside aside.

The script does not try to be a full WCAG audit. It focuses on the
patterns Chapter 7 identifies as having the highest SEO impact, and
it uses the raw HTML response (not the rendered DOM). For
JavaScript-injected structure, use heading-hierarchy-validator.js
instead, which loads the rendered DOM via Playwright.

Usage:
    python semantic-html-auditor.py --url https://example.com/
    python semantic-html-auditor.py --urls-file urls.txt
    python semantic-html-auditor.py --url https://example.com/ --output report.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 7.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# Alt text values that indicate template-level defaults rather than
# descriptive content. Case-insensitive match.
GENERIC_ALT_PATTERNS = (
    r"^image$",
    r"^images$",
    r"^photo$",
    r"^photos$",
    r"^picture$",
    r"^pictures$",
    r"^product image$",
    r"^product photo$",
    r"^thumbnail$",
    r"^icon$",
    r"^logo$",
    r"^banner$",
    r"^photo \d+$",
    r"^image \d+$",
    r"^img_\d+$",
    r"^dsc_\d+$",
    r"^untitled$",
)

# Class names and roles that suggest an element is a UI component
# whose internal headings should not pollute the document outline.
UI_COMPONENT_INDICATORS = {
    "card",
    "modal",
    "dialog",
    "popover",
    "tooltip",
    "dropdown",
    "menu",
    "sidebar",
    "widget",
    "banner",
    "tile",
}


@dataclass
class Finding:
    """A single issue found during the audit."""

    severity: str  # "high", "medium", "low"
    rule: str
    message: str
    element_excerpt: str | None = None


@dataclass
class AuditReport:
    """Aggregate audit output for a single URL."""

    url: str
    fetched: bool = False
    status_code: int | None = None
    error: str | None = None
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "fetched": self.fetched,
            "status_code": self.status_code,
            "error": self.error,
            "findings": [
                {
                    "severity": f.severity,
                    "rule": f.rule,
                    "message": f.message,
                    "element": f.element_excerpt,
                }
                for f in self.findings
            ],
            "counts": {
                "high": sum(1 for f in self.findings if f.severity == "high"),
                "medium": sum(1 for f in self.findings if f.severity == "medium"),
                "low": sum(1 for f in self.findings if f.severity == "low"),
            },
        }


def fetch(url: str) -> tuple[int, str]:
    """Fetch a URL and return status code and body."""
    response = requests.get(
        url,
        timeout=REQUEST_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.status_code, response.text


def excerpt(element: Tag, limit: int = 120) -> str:
    """Compact string representation of an element for reporting."""
    text = str(element)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 3] + "..."


def visible_text(element: Tag) -> str:
    """Visible text content of an element, stripped of whitespace."""
    return re.sub(r"\s+", " ", element.get_text(" ", strip=True))


def has_accessible_name(element: Tag) -> bool:
    """Whether an interactive element has any kind of accessible name."""
    if visible_text(element):
        return True
    if element.get("aria-label"):
        return True
    if element.get("aria-labelledby"):
        return True
    if element.get("title"):
        return True
    # Image with non-empty alt counts as an accessible name for the
    # enclosing link or button.
    for img in element.find_all("img"):
        if img.get("alt"):
            return True
    return False


def is_inside_ui_component(element: Tag) -> bool:
    """Heuristic: is this element inside a UI component root?"""
    for ancestor in element.parents:
        if not isinstance(ancestor, Tag):
            continue
        role = (ancestor.get("role") or "").lower()
        if role in {"dialog", "alertdialog", "menu", "tooltip", "menuitem"}:
            return True
        classes = " ".join(ancestor.get("class") or []).lower()
        if any(token in classes for token in UI_COMPONENT_INDICATORS):
            return True
    return False


def check_headings(soup: BeautifulSoup, report: AuditReport) -> None:
    """Check h1 uniqueness, level skipping, and aside pollution."""
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    h1_elements = [h for h in headings if h.name == "h1"]

    if not h1_elements:
        report.findings.append(
            Finding(
                severity="high",
                rule="missing_h1",
                message="Page has no <h1> element.",
            )
        )
    elif len(h1_elements) > 1:
        report.findings.append(
            Finding(
                severity="high",
                rule="multiple_h1",
                message=f"Page has {len(h1_elements)} <h1> elements. A single "
                f"<h1> per page is the recommended pattern.",
                element_excerpt=excerpt(h1_elements[1]),
            )
        )

    # Detect skipped heading levels (h2 then h4 without h3).
    last_level: int | None = None
    for heading in headings:
        level = int(heading.name[1])
        if last_level is not None and level > last_level + 1:
            report.findings.append(
                Finding(
                    severity="medium",
                    rule="skipped_heading_level",
                    message=f"Heading level jumped from h{last_level} to "
                    f"h{level} without an intervening h{last_level + 1}.",
                    element_excerpt=excerpt(heading),
                )
            )
        last_level = level

    # Headings inside aside that may pollute the outline.
    for aside in soup.find_all("aside"):
        for heading in aside.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            report.findings.append(
                Finding(
                    severity="low",
                    rule="heading_inside_aside",
                    message=f"<{heading.name}> inside <aside>. Aside headings "
                    f"appear in the document outline as sub-topics of the "
                    f"nearest preceding heading, which may not be the intent.",
                    element_excerpt=excerpt(heading),
                )
            )

    # Headings inside elements that look like UI components.
    for heading in headings:
        if is_inside_ui_component(heading):
            report.findings.append(
                Finding(
                    severity="low",
                    rule="heading_inside_ui_component",
                    message=f"<{heading.name}> appears inside a UI-component "
                    f"ancestor (card, modal, dialog, menu, sidebar). UI "
                    f"component titles usually should not be heading elements.",
                    element_excerpt=excerpt(heading),
                )
            )


def check_landmarks(soup: BeautifulSoup, report: AuditReport) -> None:
    """Check for main, header, footer, and top-level nav."""
    # Only count visible <main> elements. Hidden mains (with hidden
    # attribute) are acceptable.
    mains = [m for m in soup.find_all("main") if m.get("hidden") is None]
    if not mains:
        report.findings.append(
            Finding(
                severity="high",
                rule="missing_main",
                message="Page has no <main> element. Content extraction "
                "systems must fall back to heuristics.",
            )
        )
    elif len(mains) > 1:
        report.findings.append(
            Finding(
                severity="high",
                rule="multiple_main",
                message=f"Page has {len(mains)} visible <main> elements. "
                f"At most one is permitted.",
                element_excerpt=excerpt(mains[1]),
            )
        )

    if not soup.find("header"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_header",
                message="Page has no <header> element.",
            )
        )

    if not soup.find("footer"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_footer",
                message="Page has no <footer> element.",
            )
        )

    if not soup.find("nav"):
        report.findings.append(
            Finding(
                severity="low",
                rule="missing_nav",
                message="Page has no <nav> element. Navigation links cannot "
                "be distinguished structurally from editorial links.",
            )
        )


def check_anchors(soup: BeautifulSoup, report: AuditReport) -> None:
    """Check anchor elements for href and accessible name."""
    for a in soup.find_all("a"):
        href = a.get("href")
        # Skip in-page anchors with name attribute (legacy bookmarks).
        if href is None and a.get("name") is None and a.get("id") is None:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="anchor_without_href",
                    message="<a> element has no href. This link is not "
                    "crawlable.",
                    element_excerpt=excerpt(a),
                )
            )
            continue

        if href is not None and not has_accessible_name(a):
            report.findings.append(
                Finding(
                    severity="high",
                    rule="anchor_without_accessible_name",
                    message="<a> element has no accessible name (no text, "
                    "no aria-label, no image alt, no title). Anchor signal "
                    "is zero.",
                    element_excerpt=excerpt(a),
                )
            )


def check_buttons(soup: BeautifulSoup, report: AuditReport) -> None:
    """Check button elements for accessible name."""
    for button in soup.find_all("button"):
        if not has_accessible_name(button):
            report.findings.append(
                Finding(
                    severity="medium",
                    rule="button_without_accessible_name",
                    message="<button> has no accessible name. Often an "
                    "icon-only button missing visually hidden text.",
                    element_excerpt=excerpt(button),
                )
            )


def check_images(soup: BeautifulSoup, report: AuditReport) -> None:
    """Check images for alt attribute presence and quality."""
    generic_re = re.compile(
        "|".join(GENERIC_ALT_PATTERNS), re.IGNORECASE
    )
    for img in soup.find_all("img"):
        alt = img.get("alt")
        if alt is None:
            report.findings.append(
                Finding(
                    severity="medium",
                    rule="image_missing_alt",
                    message="<img> has no alt attribute. Decorative images "
                    "should use alt=\"\", content images should describe "
                    "the image.",
                    element_excerpt=excerpt(img),
                )
            )
            continue

        if alt and generic_re.match(alt.strip()):
            report.findings.append(
                Finding(
                    severity="medium",
                    rule="image_generic_alt",
                    message=f'<img> alt="{alt}" looks like template-level '
                    f"default alt text, not descriptive content.",
                    element_excerpt=excerpt(img),
                )
            )


def audit(url: str) -> AuditReport:
    """Run the full audit for a URL."""
    report = AuditReport(url=url)
    try:
        status, body = fetch(url)
        report.status_code = status
        report.fetched = True
    except Exception as exc:
        report.error = str(exc)
        return report

    soup = BeautifulSoup(body, "html.parser")

    check_headings(soup, report)
    check_landmarks(soup, report)
    check_anchors(soup, report)
    check_buttons(soup, report)
    check_images(soup, report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single URL to audit.")
    source.add_argument(
        "--urls-file",
        help="Path to a newline-separated list of URLs.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write JSON output to. Defaults to stdout.",
    )
    args = parser.parse_args()

    if args.url:
        urls = [args.url]
    else:
        urls = [
            line.strip()
            for line in Path(args.urls_file).read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    reports = [audit(u) for u in urls]
    out = {
        "reports": [r.to_dict() for r in reports],
        "summary": {
            "urls_audited": len(reports),
            "urls_fetched": sum(1 for r in reports if r.fetched),
            "high_severity_total": sum(
                r.to_dict()["counts"]["high"] for r in reports
            ),
            "medium_severity_total": sum(
                r.to_dict()["counts"]["medium"] for r in reports
            ),
            "low_severity_total": sum(
                r.to_dict()["counts"]["low"] for r in reports
            ),
        },
    }

    output_text = json.dumps(out, indent=2)
    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)

    # Exit non-zero if any URL has high-severity findings.
    has_high = out["summary"]["high_severity_total"] > 0
    return 1 if has_high else 0


if __name__ == "__main__":
    sys.exit(main())