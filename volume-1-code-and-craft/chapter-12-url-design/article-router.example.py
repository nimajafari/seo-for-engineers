#!/usr/bin/env python3
"""
article-router.example.py

Reference Flask route handler for the /articles/{id}/{slug} URL
pattern described in Chapter 12 of SEO for Engineers, Volume 1.
The pattern decouples readability (the slug) from identity (the
numeric ID) so the system tolerates slug changes without breaking
URLs.

How it works:

    GET /articles/12345/url-design-for-engineers
        -> 200 with the rendered article.

    GET /articles/12345/wrong-slug-here
        -> 301 redirect to /articles/12345/<canonical-slug>.

    GET /articles/12345/
    GET /articles/12345
        -> The standard Flask routing returns 404 because <slug>
           is required; if you want the slug-less form to canonicalize
           to the full URL too, add a second route below that
           captures the slug as optional and 301-redirects.

The ID is the routing key; the slug is cosmetic. If the article's
slug changes (via Article.update_slug), the redirect from old to
new slug should also be recorded in a SlugRedirect table so the
old URL still works for inbound external links.

This file is a route-handler reference, not a runnable app. The
Article model is a stub showing the shape the handler depends on.

Reference: SEO for Engineers, Volume 1, Chapter 12.
"""

from __future__ import annotations

from dataclasses import dataclass
from flask import Flask, abort, redirect, render_template, url_for

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Stub model. Replace with your ORM/data layer.
# ---------------------------------------------------------------------------


@dataclass
class Article:
    id: int
    slug: str
    title: str
    body: str

    @classmethod
    def get_or_404(cls, article_id: int) -> "Article":
        """Look up by ID, return the article or abort with 404."""
        article = _STORE.get(article_id)
        if article is None:
            abort(404)
        return article


# Trivial in-memory store so the example runs end to end. Replace
# with SQLAlchemy, Django ORM, or whatever your application uses.
_STORE: dict[int, Article] = {
    12345: Article(
        id=12345,
        slug="url-design-for-engineers",
        title="URL Design for Engineers",
        body="...",
    ),
}


# ---------------------------------------------------------------------------
# The route handler.
# ---------------------------------------------------------------------------


@app.route("/articles/<int:article_id>/<slug>")
def article_view(article_id: int, slug: str):
    """
    Serve the article. If the requested slug does not match the
    canonical slug for this article, 301-redirect to the canonical
    form so search engines consolidate signals.
    """
    article = Article.get_or_404(article_id)

    if slug != article.slug:
        canonical_url = url_for(
            "article_view",
            article_id=article_id,
            slug=article.slug,
        )
        return redirect(canonical_url, code=301)

    return render_template("article.html", article=article)


# ---------------------------------------------------------------------------
# Optional: handle the slug-less form so /articles/12345 also
# canonicalizes to /articles/12345/<canonical-slug>.
# ---------------------------------------------------------------------------


@app.route("/articles/<int:article_id>")
@app.route("/articles/<int:article_id>/")
def article_no_slug(article_id: int):
    article = Article.get_or_404(article_id)
    canonical_url = url_for(
        "article_view",
        article_id=article_id,
        slug=article.slug,
    )
    return redirect(canonical_url, code=301)


if __name__ == "__main__":
    # For quick local smoke testing: flask --app article-router.example.py run
    app.run(debug=True)
