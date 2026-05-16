#!/usr/bin/env python3
"""
soft-404-detector.py

Scan a list of URLs for soft-404 patterns described in Chapter 3 of
SEO for Engineers, Volume 1.

A soft 404 is a page that returns HTTP 200 but contains content that
indicates the page does not exist or has no meaningful content. Google
classifies these via content analysis. This script approximates that
classification with two simple signals.

  1. The visible word count is below a configurable threshold.
  2. The visible text contains one of a list of characteristic phrases.

Output is a list of URLs that match the signature, intended as a
starting point for manual review. The script makes no claim about
whether Google has actually classified any specific URL as a soft 404.

Usage:
    python soft-404-detector.py https://example.com/category/empty
    python3 soft-404-detector.py https://example.com/category/empty

    python soft-404-detector.py --urls urls.txt --csv report.csv
    python3 soft-404-detector.py --urls urls.txt --csv report.csv

    python soft-404-detector.py --urls urls.txt --csv report.csv --min-words 100
    python3 soft-404-detector.py --urls urls.txt --csv report.csv --min-words 100

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 3.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

import requests
from bs4 import BeautifulSoup

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_MIN_WORDS = 50

# Phrases that, in combination with a low word count and a 200 status,
# suggest a soft 404. Matching is case-insensitive and substring-based.
DEFAULT_SOFT_404_PHRASES = (
    "no results found",
    "no products found",
    "no posts found",
    "no items found",
    "page not found",
    "page cannot be found",
    "page could not be found",
    "page doesn't exist",
    "page does not exist",
    "currently unavailable",
    "no longer available",
    "out of stock",
    "this product is unavailable",
    "this product has been discontinued",
    "there are no results",
    "there are no posts",
    "there are no items",
    "we couldn't find",
    "we could not find",
    "error 404",
    "404 error",
    "404 not found",
)


@dataclass
class SoftFourOhFourResult:
    """Per-URL detection output."""

    url: str
    fetched: bool = False
    status_code: int | None = None
    word_count: int = 0
    matched_phrases: list[str] = field(default_factory=list)
    is_suspect: bool = False
    error: str | None = None


def extract_visible_text(html: str) -> str:
    """Return the visible text content of an HTML document, stripped."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def count_words(text: str) -> int:
    """Return a whitespace word count over the visible text."""
    return len(text.split())


def find_matching_phrases(text: str, phrases: Iterable[str]) -> list[str]:
    """Return phrases that appear (case-insensitive) in the text."""
    lower = text.lower()
    matched = []
    for phrase in phrases:
        if phrase.lower() in lower:
            matched.append(phrase)
    return matched


def detect(
    url: str,
    min_words: int,
    phrases: tuple[str, ...],
) -> SoftFourOhFourResult:
    """Check a single URL and return the result."""
    result = SoftFourOhFourResult(url=url)

    try:
        response = requests.get(
            url,
            headers={"User-Agent": GOOGLEBOT_UA},
            timeout=REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
    except Exception as exc:
        result.error = f"request failed: {exc}"
        return result

    result.fetched = True
    result.status_code = response.status_code

    # A real 4xx or 5xx is not a soft 404. The whole point of a soft 404
    # is a 200 that looks like an error.
    if response.status_code != 200:
        return result

    text = extract_visible_text(response.text)
    result.word_count = count_words(text)
    result.matched_phrases = find_matching_phrases(text, phrases)

    if result.word_count < min_words or result.matched_phrases:
        result.is_suspect = True

    return result


def load_urls(path: Path) -> list[str]:
    """Read URLs from a text file. One per line. Lines starting with # are skipped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def load_phrases(path: Path | None) -> tuple[str, ...]:
    """Load a custom phrase list from a text file, or fall back to the default."""
    if path is None:
        return DEFAULT_SOFT_404_PHRASES
    lines = path.read_text(encoding="utf-8").splitlines()
    return tuple(
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    )


def write_csv(results: Iterable[SoftFourOhFourResult], path: Path) -> None:
    """Write detection results to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "url",
                "status_code",
                "word_count",
                "matched_phrases",
                "is_suspect",
                "error",
            ]
        )
        for r in results:
            writer.writerow(
                [
                    r.url,
                    r.status_code if r.status_code is not None else "",
                    r.word_count,
                    "; ".join(r.matched_phrases),
                    "yes" if r.is_suspect else "no",
                    r.error or "",
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="A single URL to check.")
    parser.add_argument(
        "--urls",
        help="Path to a text file with one URL per line.",
    )
    parser.add_argument(
        "--csv",
        help="Write results to this CSV path. Required for batch mode.",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=DEFAULT_MIN_WORDS,
        help=f"Word count threshold. Default {DEFAULT_MIN_WORDS}.",
    )
    parser.add_argument(
        "--phrases",
        help="Path to a custom phrase list. One phrase per line.",
    )
    args = parser.parse_args()

    if args.urls and not args.csv:
        print("--urls requires --csv for batch output.", file=sys.stderr)
        return 2

    phrases = load_phrases(Path(args.phrases) if args.phrases else None)

    urls: list[str]
    if args.urls:
        urls = load_urls(Path(args.urls))
    elif args.url:
        urls = [args.url]
    else:
        print("Provide a URL or --urls <file>.", file=sys.stderr)
        return 2

    results: list[SoftFourOhFourResult] = []
    for url in urls:
        result = detect(url, min_words=args.min_words, phrases=phrases)
        results.append(result)
        if args.csv:
            tag = "SUSPECT" if result.is_suspect else "OK"
            extra = (
                f"words={result.word_count}"
                + (
                    " phrases=" + ",".join(result.matched_phrases)
                    if result.matched_phrases
                    else ""
                )
                + (f" ERROR={result.error}" if result.error else "")
            )
            print(f"{tag}\t{result.url}\t{extra}", file=sys.stderr)

    if args.csv:
        write_csv(results, Path(args.csv))
        print(f"Wrote {len(results)} rows to {args.csv}")
    else:
        for result in results:
            print(json.dumps(asdict(result), indent=2))

    return 0 if not any(r.is_suspect or r.error for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())