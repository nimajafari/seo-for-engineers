#!/usr/bin/env python3
"""
soft-404-detector.py

Scan a list of URLs for soft-404 patterns described in Chapter 3 of
SEO for Engineers, Volume 1.

A soft 404 is a page that returns HTTP 200 but contains content that
indicates the page does not exist or has no meaningful content. Google
classifies these via content analysis. This script approximates that
classification with three signals; any one of them makes a URL a
suspect, and the `signals` field says which fired.

  1. thin_content       The visible word count is below a threshold.
  2. error_phrase       The visible text contains a characteristic phrase.
  3. redirected_to_root A non-root URL redirected to the site's home page,
                        the classic way removed pages get "handled"; Google
                        treats such redirects as soft 404s.

A URL with two or more signals is a stronger candidate than one with a
single signal (a long page that merely mentions "out of stock" trips
error_phrase alone).

Output is a list of URLs that match the signature, intended as a
starting point for manual review. The script makes no claim about
whether Google has actually classified any specific URL as a soft 404.

Usage:
    python soft-404-detector.py https://example.com/category/empty
    python soft-404-detector.py --urls urls.txt --csv report.csv
    python soft-404-detector.py --urls urls.txt --csv report.csv --min-words 100

Install:
    pip install -r requirements.txt

Reference: SEO for Engineers, Volume 1, Chapter 3.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

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

# Phrases that suggest a 200 response is really an error or empty page.
# Each match is one signal on its own (see the module docstring), so the
# list favors recall; review suspects by their signal count. Matching is
# case-insensitive and substring-based.
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
    final_url: str | None = None
    word_count: int = 0
    matched_phrases: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    is_suspect: bool = False
    error: str | None = None


def header_charset(content_type: str | None) -> str | None:
    """Return the charset parameter of a Content-Type header, if any."""
    if not content_type:
        return None
    match = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", content_type, re.I)
    return match.group(1) if match else None


def extract_visible_text(html: bytes | str, content_type: str | None = None) -> str:
    """Return the visible text content of an HTML document, stripped.

    Pass the raw response bytes: BeautifulSoup then honors the header
    charset or <meta charset>, whereas requests' response.text falls back
    to ISO-8859-1 for text/html without a charset and garbles UTF-8 pages.
    """
    if isinstance(html, bytes):
        soup = BeautifulSoup(
            html, "html.parser", from_encoding=header_charset(content_type)
        )
    else:
        soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


# Han ideographs and Japanese kana are written without spaces, so a
# whitespace split counts a whole sentence as one word and flags every
# Chinese or Japanese page as thin. Count each such character as a word.
_UNSPACED = (
    "\u3040-\u30ff\u31f0-\u31ff\u3400-\u4dbf\u4e00-\u9fff"
    "\uf900-\ufaff\uff66-\uff9f"
)
_WORD_RE = re.compile(rf"[{_UNSPACED}]|[^\s{_UNSPACED}]+")


def count_words(text: str) -> int:
    """Return a word count over the visible text (Han/kana per character)."""
    return len(_WORD_RE.findall(text))


def redirected_to_root(requested_url: str, final_url: str, redirected: bool) -> bool:
    """True when a non-root URL ended, via redirects, on a site's home page."""
    if not redirected:
        return False
    requested_path = urlparse(requested_url).path or "/"
    final_path = urlparse(final_url).path or "/"
    return requested_path != "/" and final_path == "/"


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
    result.final_url = response.url

    # A real 4xx or 5xx is not a soft 404. The whole point of a soft 404
    # is a 200 that looks like an error.
    if response.status_code != 200:
        return result

    text = extract_visible_text(response.content, response.headers.get("Content-Type"))
    result.word_count = count_words(text)
    result.matched_phrases = find_matching_phrases(text, phrases)

    if result.word_count < min_words:
        result.signals.append("thin_content")
    if result.matched_phrases:
        result.signals.append("error_phrase")
    if redirected_to_root(url, response.url, bool(response.history)):
        result.signals.append("redirected_to_root")
    result.is_suspect = bool(result.signals)

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
                "signals",
                "final_url",
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
                    "; ".join(r.signals),
                    r.final_url or "",
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

    if args.min_words < 0:
        print("--min-words must be zero or more.", file=sys.stderr)
        return 2

    try:
        phrases = load_phrases(Path(args.phrases) if args.phrases else None)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Could not read --phrases file {args.phrases}: {exc}", file=sys.stderr)
        return 2

    urls: list[str]
    if args.urls:
        try:
            urls = load_urls(Path(args.urls))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"Could not read --urls file {args.urls}: {exc}", file=sys.stderr)
            return 2
        if not urls:
            print(f"No URLs found in {args.urls}.", file=sys.stderr)
            return 2
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
                (f"signals={','.join(result.signals)} " if result.signals else "")
                + f"words={result.word_count}"
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