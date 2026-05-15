# Contributing

This repository is the working substrate of the book *SEO for Engineers*.
Contributions are welcome under the rules below.

## Reporting an erratum

If you have found a factual error in the book, file an issue using the
Errata template. The template asks for:

- The volume, chapter, and page number (or section title for ebook readers).
- The current text, copied verbatim.
- The proposed correction.
- A primary source supporting the correction.

Errata that include a verifiable source from Google documentation, an IETF
RFC, the WHATWG specification, the Schema.org reference, or a confirmed
statement from a named Google engineer are accepted fastest. Errata that
rely only on a forum post or a personal observation are read but accepted
more slowly, after independent verification.

Accepted errata are added to `CHANGELOG.md` under the "Unreleased"
section and incorporated into the next printing cycle.

## Suggesting changes

For ideas, clarifications, or topic suggestions, use the Suggestion issue
template. These are reviewed monthly. Suggestions about future chapters
or future volumes are welcome but will not appear in the current edition.

## Pull requests

Pull requests are accepted for:

- Code in the chapter directories. Bug fixes, portability improvements,
  documentation improvements on the scripts, and additional diagnostic
  utilities are all in scope.
- Typo fixes in repo prose (READMEs, this file, CITATIONS, CHANGELOG).

Pull requests are not accepted for:

- Changes to the book's prose. File an Errata issue instead. The book
  text lives outside this repository.
- New chapter directories or speculative restructuring. Open a Suggestion
  issue first.

### Code style for scripts

- Shell scripts use `#!/usr/bin/env bash` and `set -euo pipefail` at the
  top.
- Python scripts target Python 3.10 or later, use only the standard
  library where possible, and include a top-level docstring describing
  what the script does, when to use it, and what to expect.
- Every script has a corresponding README entry in its chapter's
  directory.

## Maintenance commitment

This repository is maintained by the book's author. The commitment is:

- Issues acknowledged within two weeks.
- Errata reviewed and folded into the next printing.
- Pull requests reviewed monthly.

If an issue has not been acknowledged within two weeks, leave a short
reply on the issue itself to surface it.
