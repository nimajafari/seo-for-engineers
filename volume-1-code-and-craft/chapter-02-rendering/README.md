# Chapter 2, The Rendering Pipeline

This directory contains the diagnostic scripts referenced in Chapter 2 of
*SEO for Engineers, Volume 1*. The scripts help you see the gap between
what Googlebot sees in wave one (raw HTML) and what it sees in wave two
(rendered DOM).

## Scripts

### `compare-raw-vs-rendered.sh`

Fetches a URL twice with curl: once with the Googlebot user-agent and
once with a desktop-browser user-agent, printing both responses with a
banner between them.

Because curl does not execute JavaScript, the delta between the two
responses is **not** the client-side rendering gap. It is whatever the
server returns differently for the two user-agents, which surfaces
user-agent-adaptive serving and cloaking. For a client-rendered SPA both
fetches typically return the same shell, so this script shows no
difference even when the JavaScript rendering gap is large. To measure
that gap — content injected after load — use `rendering-debt-audit.py`,
which runs a real headless browser.

Usage:
./compare-raw-vs-rendered.sh https://example.com/page

The script prints both responses to stdout, separated by a banner. For a
machine-readable diff, pipe each side into a file and run `diff`.

### `rendering-debt-audit.py`

Measures the rendering debt of a URL by comparing the visible text in
the raw HTTP response against the visible text in the rendered DOM. This
is the implementation of the audit framework described in the chapter's
Manager Lens section.

Both sides are tokenized into case-folded word multisets. The score is
the share of rendered tokens (counted with multiplicity) that do not
appear in the raw response. A score of 0 means every word in the
rendered DOM is already present, in at least the same count, in the raw
HTML, which is the ideal. A score of 0.8 means 80% of the rendered word
occurrences are rendering-dependent, which is a strong signal that the
page relies on client-side rendering for content that should be in the
initial HTTP response.

Usage:
Single URL
python rendering-debt-audit.py https://example.com/page
Batch mode, one URL per line in a text file, CSV output
python rendering-debt-audit.py --urls urls.txt --csv report.csv

Requires Python 3.10 or later. Install dependencies first.
pip install -r requirements.txt
playwright install chromium

The Playwright browser install is a one-time download of around 150MB.

### `dom-byte-counter.js`

A small browser-console snippet that samples the size of `document.body`
at two moments. Once at paste time (the post-parse DOM) and once five
seconds later (after most async work has settled). The delta tells you
how much of the page's content arrives after the initial parse.

Usage. Load the page you want to inspect. Open DevTools and switch to
the Console tab. Paste the contents of the file into the console and
press Enter. Wait five seconds. Read the two console logs.

Do not reload after pasting. A reload replaces the document and
detaches anything you set up in the console, so the deferred sample
would never run. Paste against the already-loaded page instead.

This is a quick sanity check, not a rigorous measurement. For real
audits use `rendering-debt-audit.py`.

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.