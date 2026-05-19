"""
normalize_query.py

Parameter-order normalization for category page URLs. Two duplicate
URLs with parameters in different orders (?color=black&size=10 vs
?size=10&color=black) produce the same content but split link equity
and double the crawl cost. Normalizing the order server-side and
301-redirecting non-canonical orderings collapses the duplication.

The module provides a framework-agnostic core function plus thin
adapters for Django and Flask. Wire one up to every view that
accepts query parameters.
"""

from __future__ import annotations

from typing import Callable
from urllib.parse import parse_qsl, urlencode


def canonicalize_query_string(query_string: str) -> str:
    """Return the canonical form of a query string.

    Normalization rules:
      - Parameters sorted alphabetically by key.
      - Values lowercased and stripped of surrounding whitespace.
      - Empty values dropped.
      - Multi-valued parameters preserve their original order within key.

    Returns the same string if it is already canonical.
    """
    pairs = parse_qsl(query_string, keep_blank_values=False)

    cleaned = [
        (key, value.lower().strip())
        for key, value in pairs
        if value.strip()
    ]

    # Sort by key, but preserve original order of values within a key.
    cleaned.sort(key=lambda kv: kv[0])

    return urlencode(cleaned)


def should_normalize(path: str) -> bool:
    """Predicate controlling which paths get normalization.

    Override to skip paths where parameter order matters semantically:
    signed API endpoints, OAuth flows, payment callbacks. Default is
    to normalize everything.
    """
    return True


# Django adapter
try:
    from django.http import HttpResponsePermanentRedirect

    def normalize_query_redirect(view_func: Callable) -> Callable:
        """Django decorator. 301 to the canonical query order if needed."""
        def wrapper(request, *args, **kwargs):
            if not should_normalize(request.path):
                return view_func(request, *args, **kwargs)
            if not request.GET:
                return view_func(request, *args, **kwargs)

            raw_qs = request.META.get("QUERY_STRING", "")
            canonical_qs = canonicalize_query_string(raw_qs)

            if canonical_qs != raw_qs:
                target = request.path
                if canonical_qs:
                    target = f"{target}?{canonical_qs}"
                return HttpResponsePermanentRedirect(target)

            return view_func(request, *args, **kwargs)

        wrapper.__name__ = view_func.__name__
        wrapper.__doc__ = view_func.__doc__
        return wrapper

except ImportError:
    def normalize_query_redirect(_view_func: Callable) -> Callable:
        raise RuntimeError(
            "normalize_query_redirect requires Django. "
            "Install Django (pip install django) or use the framework-agnostic "
            "canonicalize_query_string() directly."
        )


# Flask adapter
try:
    from flask import request as flask_request, redirect

    def flask_normalize_query():
        """Flask before_request hook. 301 to the canonical query order."""
        if not should_normalize(flask_request.path):
            return None
        if not flask_request.query_string:
            return None

        raw_qs = flask_request.query_string.decode("utf-8")
        canonical_qs = canonicalize_query_string(raw_qs)

        if canonical_qs != raw_qs:
            target = flask_request.path
            if canonical_qs:
                target = f"{target}?{canonical_qs}"
            return redirect(target, code=301)

        return None

except ImportError:
    def flask_normalize_query():
        raise RuntimeError(
            "flask_normalize_query requires Flask. "
            "Install Flask (pip install flask) or use the framework-agnostic "
            "canonicalize_query_string() directly."
        )