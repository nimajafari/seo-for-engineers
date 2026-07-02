#!/usr/bin/env python3
"""
structured-data-extractor.py

Fetch a URL (or a list of URLs), extract all JSON-LD blocks from the
raw HTML response, parse each block, and validate it against a registry
of per-type rules covering Google's required-field requirements for
the schema types Chapter 9 of SEO for Engineers, Volume 1, identifies
as highest value.

This reads the raw HTTP response, so JSON-LD injected client-side (e.g.
by Google Tag Manager) is not captured. To validate JSON-LD in the
rendered DOM, use schema-consistency-checker.js in this directory, which
loads the page in a real browser.

Severity buckets:

  High severity. Invalid JSON syntax, missing required Schema.org or
  Google fields for a declared type, deprecated rich-result types,
  unsanitized HTML-significant characters in string values.

  Medium severity. Missing strongly recommended fields, missing
  sameAs on Organization or Person, availability values outside the
  Schema.org enumeration.

  Low severity. Missing optional but valuable fields.

Usage:
    python structured-data-extractor.py --url https://example.com/
    python structured-data-extractor.py --urls-file urls.txt
    python structured-data-extractor.py --url https://example.com/ --output report.json

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 9.
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
from bs4 import BeautifulSoup

REQUEST_TIMEOUT_SECONDS = 20
USER_AGENT = (
    "Mozilla/5.0 (compatible; SeoForEngineersAuditor/1.0; "
    "+https://github.com/nimajafari/seo-for-engineers)"
)

# Deprecated rich-result types as of May 2026. Implementing these
# produces dead code per Chapter 9, Failure Mode 7.
DEPRECATED_TYPES = {
    "BookAction",
    "ReadAction",
    "BorrowAction",
    "Course",
    "CourseInfo",
    "ClaimReview",
    "EstimatedSalary",
    "Occupation",
    "LearningVideo",
    "LearningResource",
    "SpecialAnnouncement",
    "Vehicle",
    "Car",
    "VehicleListing",
    "PracticeProblem",
    "Quiz",
    "Question",  # In legacy FAQPage context only, flagged separately
    "FAQPage",
    "HowTo",
}

# Google's documented availability enumeration. Anything outside this
# set is a medium-severity finding.
VALID_AVAILABILITY = {
    "https://schema.org/InStock",
    "https://schema.org/OutOfStock",
    "https://schema.org/OnlineOnly",
    "https://schema.org/InStoreOnly",
    "https://schema.org/PreOrder",
    "https://schema.org/PreSale",
    "https://schema.org/BackOrder",
    "https://schema.org/SoldOut",
    "https://schema.org/Discontinued",
    "https://schema.org/LimitedAvailability",
}

# Leaf names of the availability enum, so the check accepts the
# https://, http://, and bare-name forms Google all treat as valid
# (comparing full https:// URLs alone would flag valid http:// markup).
VALID_AVAILABILITY_NAMES = {url.rsplit("/", 1)[-1] for url in VALID_AVAILABILITY}

# Currency code regex (ISO 4217).
ISO_4217_RE = re.compile(r"^[A-Z]{3}$")

# Indicators that a string contains unsanitized HTML.
HTML_SIGNIFICANT_RE = re.compile(r"<\s*/?\s*script", re.IGNORECASE)


@dataclass
class Finding:
    """A single issue found during validation."""

    severity: str  # "high", "medium", "low"
    rule: str
    message: str
    schema_type: str | None = None
    field: str | None = None


@dataclass
class BlockReport:
    """Validation output for a single JSON-LD block."""

    index: int
    schema_type: str | None
    findings: list[Finding] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class PageReport:
    """Aggregate audit output for a single URL."""

    url: str
    fetched: bool = False
    status_code: int | None = None
    error: str | None = None
    block_count: int = 0
    blocks: list[BlockReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        all_findings = [
            f for b in self.blocks for f in b.findings
        ]
        return {
            "url": self.url,
            "fetched": self.fetched,
            "status_code": self.status_code,
            "error": self.error,
            "block_count": self.block_count,
            "blocks": [
                {
                    "index": b.index,
                    "schema_type": b.schema_type,
                    "parse_error": b.parse_error,
                    "findings": [
                        {
                            "severity": f.severity,
                            "rule": f.rule,
                            "message": f.message,
                            "schema_type": f.schema_type,
                            "field": f.field,
                        }
                        for f in b.findings
                    ],
                }
                for b in self.blocks
            ],
            "counts": {
                "high": sum(1 for f in all_findings if f.severity == "high"),
                "medium": sum(1 for f in all_findings if f.severity == "medium"),
                "low": sum(1 for f in all_findings if f.severity == "low"),
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


def extract_jsonld_blocks(html: str) -> list[tuple[int, str]]:
    """Return (index, raw_text) for each application/ld+json script."""
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for index, script in enumerate(
        soup.find_all("script", attrs={"type": "application/ld+json"})
    ):
        text = script.string or script.text or ""
        blocks.append((index, text.strip()))
    return blocks


def get_type(obj: Any) -> str | None:
    """Return @type as a string, even if the value is an array."""
    if not isinstance(obj, dict):
        return None
    t = obj.get("@type")
    if isinstance(t, list) and t:
        return str(t[0])
    if isinstance(t, str):
        return t
    return None


def flatten_blocks(parsed: Any) -> list[dict]:
    """Flatten arrays and @graph into a list of top-level objects."""
    if isinstance(parsed, list):
        out = []
        for item in parsed:
            out.extend(flatten_blocks(item))
        return out
    if isinstance(parsed, dict):
        graph = parsed.get("@graph")
        if isinstance(graph, list):
            return graph
        return [parsed]
    return []


def find_unsanitized_strings(
    obj: Any, path: str = ""
) -> list[tuple[str, str]]:
    """Find string values that contain unsanitized script-tag markers."""
    findings = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            findings.extend(find_unsanitized_strings(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            findings.extend(find_unsanitized_strings(item, f"{path}[{i}]"))
    elif isinstance(obj, str):
        if HTML_SIGNIFICANT_RE.search(obj):
            findings.append((path.lstrip("."), obj))
    return findings


def check_deprecated_type(
    obj: dict, schema_type: str, report: BlockReport
) -> None:
    """Flag deprecated rich-result types from the chapter."""
    if schema_type in DEPRECATED_TYPES:
        # Question is only deprecated as the primary type of an FAQPage.
        # A Question inside a QAPage is still supported.
        if schema_type == "Question":
            return
        report.findings.append(
            Finding(
                severity="high",
                rule="deprecated_type",
                message=f"Schema type '{schema_type}' is no longer "
                f"supported by Google for rich results as of 2025-2026. "
                f"Remove this markup or replace it with a supported type.",
                schema_type=schema_type,
            )
        )


def check_product(obj: dict, report: BlockReport) -> None:
    """Validate Product against Google's required-field requirements."""
    # Google requires at minimum: name, image, and one of review,
    # aggregateRating, or offers.
    if not obj.get("name"):
        report.findings.append(
            Finding(
                severity="high",
                rule="product_missing_name",
                message="Product is missing required 'name' field.",
                schema_type="Product",
                field="name",
            )
        )

    if not obj.get("image"):
        report.findings.append(
            Finding(
                severity="high",
                rule="product_missing_image",
                message="Product is missing required 'image' field.",
                schema_type="Product",
                field="image",
            )
        )

    if not any(obj.get(f) for f in ("offers", "review", "aggregateRating")):
        report.findings.append(
            Finding(
                severity="high",
                rule="product_no_offer_or_rating",
                message="Product must have at least one of 'offers', "
                "'review', or 'aggregateRating' to be eligible for "
                "rich results.",
                schema_type="Product",
            )
        )

    # Identity fields (SKU or GTIN) help Google resolve the product.
    if not any(
        obj.get(f) for f in ("sku", "gtin", "gtin8", "gtin12", "gtin13", "gtin14", "mpn")
    ):
        report.findings.append(
            Finding(
                severity="low",
                rule="product_no_identifier",
                message="Product has no SKU, GTIN, or MPN. Without an "
                "identifier, Google must infer which product you are "
                "describing, which is less reliable.",
                schema_type="Product",
            )
        )

    # Validate nested Offer.
    offers = obj.get("offers")
    if isinstance(offers, dict):
        check_offer(offers, report)
    elif isinstance(offers, list):
        for o in offers:
            if isinstance(o, dict):
                check_offer(o, report)

    # Validate nested AggregateRating.
    rating = obj.get("aggregateRating")
    if isinstance(rating, dict):
        check_aggregate_rating(rating, report)


def check_offer(obj: dict, report: BlockReport) -> None:
    """Validate Offer against Google's required-field requirements."""
    required = ("price", "priceCurrency", "availability")
    for f in required:
        if f not in obj:
            report.findings.append(
                Finding(
                    severity="high",
                    rule=f"offer_missing_{f}",
                    message=f"Offer is missing required '{f}' field.",
                    schema_type="Offer",
                    field=f,
                )
            )

    currency = obj.get("priceCurrency")
    if currency and not ISO_4217_RE.match(str(currency)):
        report.findings.append(
            Finding(
                severity="high",
                rule="offer_invalid_currency",
                message=f"Offer priceCurrency '{currency}' is not a "
                f"valid ISO 4217 code.",
                schema_type="Offer",
                field="priceCurrency",
            )
        )

    availability = obj.get("availability")
    if availability and str(availability).rsplit("/", 1)[-1] not in VALID_AVAILABILITY_NAMES:
        report.findings.append(
            Finding(
                severity="medium",
                rule="offer_unknown_availability",
                message=f"Offer availability '{availability}' is not in "
                f"the Schema.org enumeration. Use one of: "
                f"InStock, OutOfStock, PreOrder, BackOrder, SoldOut, "
                f"Discontinued, LimitedAvailability.",
                schema_type="Offer",
                field="availability",
            )
        )


def check_aggregate_rating(obj: dict, report: BlockReport) -> None:
    """Validate AggregateRating."""
    if "ratingValue" not in obj:
        report.findings.append(
            Finding(
                severity="high",
                rule="rating_missing_value",
                message="AggregateRating is missing required 'ratingValue'.",
                schema_type="AggregateRating",
                field="ratingValue",
            )
        )
    if "reviewCount" not in obj and "ratingCount" not in obj:
        report.findings.append(
            Finding(
                severity="high",
                rule="rating_missing_count",
                message="AggregateRating must have either 'reviewCount' "
                "or 'ratingCount'.",
                schema_type="AggregateRating",
            )
        )


def check_article(obj: dict, report: BlockReport, schema_type: str) -> None:
    """Validate Article-family types."""
    if not obj.get("headline"):
        report.findings.append(
            Finding(
                severity="high",
                rule="article_missing_headline",
                message=f"{schema_type} is missing required 'headline'.",
                schema_type=schema_type,
                field="headline",
            )
        )
    if not obj.get("image"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="article_missing_image",
                message=f"{schema_type} is missing 'image', which Google "
                "strongly recommends.",
                schema_type=schema_type,
                field="image",
            )
        )
    if not obj.get("datePublished"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="article_missing_date_published",
                message=f"{schema_type} is missing 'datePublished'.",
                schema_type=schema_type,
                field="datePublished",
            )
        )
    if not obj.get("author"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="article_missing_author",
                message=f"{schema_type} is missing 'author'. Author "
                "attribution is increasingly important for E-E-A-T "
                "signals and Knowledge Graph entity resolution.",
                schema_type=schema_type,
                field="author",
            )
        )


def check_breadcrumb_list(obj: dict, report: BlockReport) -> None:
    """Validate BreadcrumbList."""
    items = obj.get("itemListElement")
    if not isinstance(items, list) or not items:
        report.findings.append(
            Finding(
                severity="high",
                rule="breadcrumb_missing_items",
                message="BreadcrumbList must have a non-empty "
                "'itemListElement' array.",
                schema_type="BreadcrumbList",
                field="itemListElement",
            )
        )
        return

    seen_positions = set()
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        pos = item.get("position")
        if pos is None:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="breadcrumb_item_missing_position",
                    message=f"BreadcrumbList item at index {i} is missing "
                    "'position'.",
                    schema_type="ListItem",
                )
            )
        elif pos in seen_positions:
            report.findings.append(
                Finding(
                    severity="high",
                    rule="breadcrumb_duplicate_position",
                    message=f"BreadcrumbList has duplicate position {pos}.",
                    schema_type="ListItem",
                )
            )
        seen_positions.add(pos)

        if not item.get("name"):
            report.findings.append(
                Finding(
                    severity="high",
                    rule="breadcrumb_item_missing_name",
                    message=f"BreadcrumbList item at position {pos} is "
                    "missing 'name'.",
                    schema_type="ListItem",
                )
            )


def check_recipe(obj: dict, report: BlockReport) -> None:
    """Validate Recipe."""
    for f in ("name", "image", "recipeIngredient", "recipeInstructions"):
        if not obj.get(f):
            report.findings.append(
                Finding(
                    severity="high",
                    rule=f"recipe_missing_{f}",
                    message=f"Recipe is missing required '{f}'.",
                    schema_type="Recipe",
                    field=f,
                )
            )


def check_event(obj: dict, report: BlockReport) -> None:
    """Validate Event."""
    for f in ("name", "startDate", "location"):
        if not obj.get(f):
            report.findings.append(
                Finding(
                    severity="high",
                    rule=f"event_missing_{f}",
                    message=f"Event is missing required '{f}'.",
                    schema_type="Event",
                    field=f,
                )
            )


def check_local_business(obj: dict, report: BlockReport, schema_type: str) -> None:
    """Validate LocalBusiness and subtypes."""
    for f in ("name", "address"):
        if not obj.get(f):
            report.findings.append(
                Finding(
                    severity="high",
                    rule=f"localbusiness_missing_{f}",
                    message=f"{schema_type} is missing required '{f}'.",
                    schema_type=schema_type,
                    field=f,
                )
            )

    if not obj.get("telephone") and not obj.get("url"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="localbusiness_no_contact",
                message=f"{schema_type} has neither 'telephone' nor 'url'. "
                "At least one contact mechanism is recommended.",
                schema_type=schema_type,
            )
        )


def check_organization(obj: dict, report: BlockReport) -> None:
    """Validate Organization."""
    if not obj.get("name"):
        report.findings.append(
            Finding(
                severity="high",
                rule="organization_missing_name",
                message="Organization is missing required 'name'.",
                schema_type="Organization",
                field="name",
            )
        )
    if not obj.get("url"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="organization_missing_url",
                message="Organization is missing 'url', which helps Google "
                "resolve the entity.",
                schema_type="Organization",
                field="url",
            )
        )
    if not obj.get("sameAs"):
        report.findings.append(
            Finding(
                severity="medium",
                rule="organization_missing_same_as",
                message="Organization is missing 'sameAs'. Links to "
                "Wikipedia, Wikidata, LinkedIn, and official social "
                "profiles help Google resolve the entity to the "
                "Knowledge Graph.",
                schema_type="Organization",
                field="sameAs",
            )
        )


def check_video_object(obj: dict, report: BlockReport) -> None:
    """Validate VideoObject."""
    for f in ("name", "description", "thumbnailUrl", "uploadDate"):
        if not obj.get(f):
            report.findings.append(
                Finding(
                    severity="high",
                    rule=f"video_missing_{f}",
                    message=f"VideoObject is missing required '{f}'.",
                    schema_type="VideoObject",
                    field=f,
                )
            )


# Type-name (including subtype) to validator function.
LOCAL_BUSINESS_SUBTYPES = {
    "LocalBusiness", "Restaurant", "Store", "MedicalBusiness", "MedicalClinic",
    "LegalService", "FinancialService", "AutomotiveBusiness", "ChildCare",
    "DryCleaningOrLaundry", "EmergencyService", "EmploymentAgency",
    "EntertainmentBusiness", "FoodEstablishment", "GovernmentOffice",
    "HealthAndBeautyBusiness", "HomeAndConstructionBusiness", "LodgingBusiness",
    "ProfessionalService", "RadioStation", "RealEstateAgent", "RecyclingCenter",
    "SelfStorage", "ShoppingCenter", "SportsActivityLocation", "TelevisionStation",
    "TouristInformationCenter", "TravelAgency",
}

ARTICLE_TYPES = {"Article", "NewsArticle", "BlogPosting", "TechArticle"}


def validate_block(obj: dict, report: BlockReport) -> None:
    """Run all validation checks for a single JSON-LD object."""
    schema_type = get_type(obj)
    report.schema_type = schema_type

    if not schema_type:
        # No @type, this is unusual but not always wrong.
        return

    check_deprecated_type(obj, schema_type, report)

    if schema_type == "Product":
        check_product(obj, report)
    elif schema_type in ARTICLE_TYPES:
        check_article(obj, report, schema_type)
    elif schema_type == "BreadcrumbList":
        check_breadcrumb_list(obj, report)
    elif schema_type == "Recipe":
        check_recipe(obj, report)
    elif schema_type == "Event":
        check_event(obj, report)
    elif schema_type in LOCAL_BUSINESS_SUBTYPES:
        check_local_business(obj, report, schema_type)
    elif schema_type == "Organization":
        check_organization(obj, report)
    elif schema_type == "VideoObject":
        check_video_object(obj, report)
    elif schema_type == "Offer":
        check_offer(obj, report)
    elif schema_type == "AggregateRating":
        check_aggregate_rating(obj, report)

    # Universal sanitization check.
    unsafe = find_unsanitized_strings(obj)
    for path, value in unsafe:
        report.findings.append(
            Finding(
                severity="high",
                rule="unsanitized_user_content",
                message=f"Field '{path}' contains script-tag-like markup "
                f"that has not been escaped. This is the XSS pattern from "
                f"Failure Mode 8. Sanitize by escaping < as \\u003c.",
                schema_type=schema_type,
                field=path,
            )
        )


def audit(url: str) -> PageReport:
    """Run the full audit for a URL."""
    report = PageReport(url=url)
    try:
        status, body = fetch(url)
        report.status_code = status
        report.fetched = True
    except Exception as exc:
        report.error = str(exc)
        return report

    raw_blocks = extract_jsonld_blocks(body)
    report.block_count = len(raw_blocks)

    for index, raw in raw_blocks:
        block_report = BlockReport(index=index, schema_type=None)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            block_report.parse_error = f"{exc.__class__.__name__}: {exc}"
            block_report.findings.append(
                Finding(
                    severity="high",
                    rule="invalid_json",
                    message=f"JSON-LD block {index} is not valid JSON: {exc}",
                )
            )
            report.blocks.append(block_report)
            continue

        # The block may be a single object, an array, or have @graph.
        flat = flatten_blocks(parsed)
        for obj in flat:
            if isinstance(obj, dict):
                validate_block(obj, block_report)

        report.blocks.append(block_report)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Single URL to audit.")
    source.add_argument(
        "--urls-file",
        help="Newline-separated list of URLs.",
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
            if line.strip() and not line.strip().startswith("#")
        ]

    reports = []
    for url in urls:
        report = audit(url)
        reports.append(report)
        counts = report.to_dict()["counts"]
        status = "OK" if counts["high"] == 0 else "FAIL"
        print(
            f"{status}\t{url}\tblocks={report.block_count} "
            f"h={counts['high']} m={counts['medium']} l={counts['low']}",
            file=sys.stderr,
        )

    out = {
        "reports": [r.to_dict() for r in reports],
        "summary": {
            "urls_audited": len(reports),
            "urls_fetched": sum(1 for r in reports if r.fetched),
            "blocks_total": sum(r.block_count for r in reports),
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

    return 1 if out["summary"]["high_severity_total"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())