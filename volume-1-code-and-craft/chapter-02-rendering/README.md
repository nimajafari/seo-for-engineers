# Chapter 2, The Rendering Pipeline

This directory contains the diagnostic scripts referenced in Chapter 2 of
*SEO for Engineers, Volume 1*. The scripts help you see the gap between
what Googlebot sees in wave one (raw HTML) and what it sees in wave two
(rendered DOM).

## Setup

The scripts in this chapter are Python; the rendering audit drives the
Playwright Python package. From this directory:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

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

```bash
# Print both responses, then a summary
./compare-raw-vs-rendered.sh https://example.com/page

# Save the bodies as out/googlebot.html and out/browser.html for diff
./compare-raw-vs-rendered.sh https://example.com/page out/
diff out/googlebot.html out/browser.html
```

Both modes end with a summary showing each user-agent's HTTP status,
final URL after redirects, and body size, and they flag a status or
redirect target that differs between the two. A 403 or a different
redirect for Googlebot is a user-agent-adaptive serving finding even
when the bodies look alike. The script exits 0 when both fetches
complete, whatever their HTTP status, and exits 2 when a fetch fails
outright (DNS, connection, TLS, timeout).

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

How the two sides are compared:

- **Body text only.** The raw side reads `<body>`, minus `script`,
  `style`, `noscript` and `template`, to match `document.body.innerText`
  on the rendered side.
- **Charset as a browser reads it.** The raw HTML is decoded using the
  `Content-Type` charset, or the page's `<meta charset>` when the header
  has none. (`requests` alone would fall back to ISO-8859-1 and garble
  every non-ASCII word of a UTF-8 page, inflating the score.)
- **Unspaced scripts.** Han and Japanese kana characters count as one
  token each, since those scripts don't put spaces between words.

Usage:

```bash
# Single URL, JSON output
python rendering-debt-audit.py https://example.com/page

# Batch mode, one URL per line in a text file, CSV output
python rendering-debt-audit.py --urls urls.txt --csv report.csv
```

The script exits 1 if any URL produced an error, so it can gate CI, and
exits 2 for a usage problem such as an unreadable or empty `--urls`
file. Errors are kept to one line per URL. Expect some sites to return
403 to the raw fetch: bot protection blocks a Googlebot user-agent that
doesn't come from Google's IP ranges.

Requires Python 3.10 or later; see Setup above. The Playwright browser
install is a one-time download of around 150MB.

### `dom-byte-counter.js`

A small browser-console snippet that samples the size of `document.body`,
in UTF-8 bytes, at two moments. Once at paste time (the post-parse DOM) and once five
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

## Tests

From this directory, after Setup:

```bash
python3 -m pytest -q   # audit and compare-script tests
node --test            # dom-byte-counter.js
```

Or from the repo root: `make test-chapter-02-rendering`,
`make test-js-chapter-02-rendering`, and `make test-sh-chapter-02-rendering`.

Most of the suite runs offline. The compare-script tests put a stub
`curl` first on `PATH`, and the console snippet runs in a `node:vm`
sandbox with a fake `document`. One end-to-end test renders pages from a
local HTTP server in Chromium. It is skipped if the Playwright browser
isn't installed.

## Primary sources

The scripts and the chapter both reference the same primary sources. See
the top-level [`CITATIONS.md`](../../CITATIONS.md) for the full list.