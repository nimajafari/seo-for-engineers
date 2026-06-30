#!/usr/bin/env python3
"""
rendering-debt-audit.py

Measure the rendering debt of a URL by comparing the visible text in the
raw HTTP response against the visible text in the rendered DOM.

Both sides are tokenized into case-folded word multisets. The rendering
debt score is the share of rendered tokens (counted with multiplicity)
that do not appear in the raw response. A score of 0 means every word
in the rendered DOM is already present, in at least the same count, in
the raw HTML. A score of 0.8 means 80% of the rendered word occurrences
are rendering-dependent.

Usage:
    python rendering-debt-audit.py https://example.com/page
    python rendering-debt-audit.py --urls urls.txt --csv report.csv

Install:
    pip install -r requirements.txt
    playwright install chromium

Reference: SEO for Engineers, Volume 1, Chapter 2.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.async_api import Browser, async_playwright

GOOGLEBOT_UA = (
    "Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/W.X.Y.Z "
    "Mobile Safari/537.36 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

REQUEST_TIMEOUT_SECONDS = 20
RENDER_TIMEOUT_MS = 30_000
RENDER_NETWORK_IDLE_MS = 2_000


@dataclass
class AuditResult:
    """Per-URL audit output."""

    url: str
    raw_word_count: int
    rendered_word_count: int
    rendering_debt_score: float
    error: str | None = None

    @property
    def score_pct(self) -> str:
        """Format the rendering debt score as a percentage."""
        return f"{self.rendering_debt_score:.0%}"


def fetch_raw_text(url: str) -> str:
    """Fetch the URL with the Googlebot user-agent and return visible text."""
    response = requests.get(
        url,
        headers={"User-Agent": GOOGLEBOT_UA},
        timeout=REQUEST_TIMEOUT_SECONDS,
        allow_redirects=True,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    # Remove script and style content, which is not visible to a reader.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


async def fetch_rendered_text(url: str, browser: Browser) -> str:
    """Render the URL in headless Chromium and return visible body text.

    The browser is shared across URLs; each call gets a fresh context so
    cookies and storage stay isolated without re-paying the launch cost.
    """
    context = await browser.new_context(user_agent=GOOGLEBOT_UA)
    try:
        page = await context.new_page()
        await page.goto(url, timeout=RENDER_TIMEOUT_MS, wait_until="load")
        # Wait briefly for network-idle, which approximates the end of
        # most async work. Capped by RENDER_NETWORK_IDLE_MS to keep the
        # audit responsive on pages that never reach idle.
        try:
            await page.wait_for_load_state(
                "networkidle", timeout=RENDER_NETWORK_IDLE_MS
            )
        except Exception:
            # networkidle is best-effort, not fatal.
            pass
        return await page.evaluate("() => document.body.innerText")
    finally:
        await context.close()


_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)


def tokenize(text: str) -> Counter[str]:
    """Return a case-folded multiset of word tokens from text."""
    return Counter(m.group(0).lower() for m in _TOKEN_RE.finditer(text))


def compute_score(raw_tokens: Counter[str], rendered_tokens: Counter[str]) -> float:
    """Return the rendering debt score: the share of rendered tokens
    (counted with multiplicity) that do not appear in the raw response."""
    rendered_total = sum(rendered_tokens.values())
    if rendered_total <= 0:
        return 0.0
    # Counter subtraction drops zero/negative counts, so this yields
    # rendered tokens beyond what the raw response already contained.
    new_in_rendered = sum((rendered_tokens - raw_tokens).values())
    score = new_in_rendered / rendered_total
    return max(0.0, min(1.0, score))


async def audit(url: str, browser: Browser) -> AuditResult:
    """Audit a single URL and return the result."""
    try:
        raw_text = fetch_raw_text(url)
        rendered_text = await fetch_rendered_text(url, browser)
    except Exception as exc:
        return AuditResult(
            url=url,
            raw_word_count=0,
            rendered_word_count=0,
            rendering_debt_score=0.0,
            error=str(exc),
        )

    raw_tokens = tokenize(raw_text)
    rendered_tokens = tokenize(rendered_text)
    score = compute_score(raw_tokens, rendered_tokens)
    return AuditResult(
        url=url,
        raw_word_count=sum(raw_tokens.values()),
        rendered_word_count=sum(rendered_tokens.values()),
        rendering_debt_score=score,
    )


def load_urls(path: Path) -> list[str]:
    """Read URLs from a text file, one per line, ignoring blanks and comments."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


def write_csv(results: list[AuditResult], path: Path) -> None:
    """Write audit results to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "url",
                "raw_word_count",
                "rendered_word_count",
                "rendering_debt_score",
                "rendering_debt_pct",
                "error",
            ]
        )
        for result in results:
            writer.writerow(
                [
                    result.url,
                    result.raw_word_count,
                    result.rendered_word_count,
                    f"{result.rendering_debt_score:.4f}",
                    result.score_pct,
                    result.error or "",
                ]
            )


async def main_async(args: argparse.Namespace) -> int:
    urls: list[str]
    if args.urls:
        urls = load_urls(Path(args.urls))
    elif args.url:
        urls = [args.url]
    else:
        print("Provide a URL or --urls <file>.", file=sys.stderr)
        return 2

    def progress(result: AuditResult) -> None:
        if args.csv:
            # Stream progress to stderr while still writing CSV at the end.
            print(
                f"{result.url}\t{result.score_pct}\t"
                f"raw={result.raw_word_count} rendered={result.rendered_word_count}"
                + (f"\tERROR: {result.error}" if result.error else ""),
                file=sys.stderr,
            )

    results: list[AuditResult] = []
    # Launch Chromium once and reuse it across URLs; each audit runs in a
    # fresh context. Re-launching per URL also restarts the Playwright
    # driver, which dominates wall-clock time on batch runs.
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as exc:
            # A launch failure (e.g. `playwright install chromium` was never
            # run) is reported once per URL so batch output stays complete.
            for url in urls:
                result = AuditResult(
                    url=url,
                    raw_word_count=0,
                    rendered_word_count=0,
                    rendering_debt_score=0.0,
                    error=str(exc),
                )
                results.append(result)
                progress(result)
        else:
            try:
                for url in urls:
                    result = await audit(url, browser)
                    results.append(result)
                    progress(result)
            finally:
                await browser.close()

    if args.csv:
        write_csv(results, Path(args.csv))
        print(f"Wrote {len(results)} rows to {args.csv}")
    else:
        # Default human-readable output for single-URL invocations.
        for result in results:
            print(json.dumps(asdict(result), indent=2))

    # Exit non-zero if any audit produced an error, so the script can be
    # used in CI pipelines.
    return 0 if all(r.error is None for r in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="A single URL to audit.")
    parser.add_argument(
        "--urls",
        help="Path to a text file with one URL per line. Lines starting "
        "with # are ignored.",
    )
    parser.add_argument(
        "--csv",
        help="Write results to this CSV path. Required for batch mode.",
    )
    args = parser.parse_args()

    if args.urls and not args.csv:
        print("--urls requires --csv for batch output.", file=sys.stderr)
        return 2

    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())