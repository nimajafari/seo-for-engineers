"""Shared fixtures: script loading and a local HTTP server.

The scripts are loaded via importlib because their filenames use
hyphens. The server serves canned responses from a routes table so the
end-to-end tests run offline with full control over status codes,
headers, and redirects.
"""

from __future__ import annotations

import http.server
import importlib.util
import sys
import threading
from pathlib import Path

import pytest

CHAPTER = Path(__file__).resolve().parent.parent


def load_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, CHAPTER / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module  # dataclasses resolve annotations here
    spec.loader.exec_module(module)
    return module


class Route:
    """A canned response. `body` may use {origin} for the server origin."""

    def __init__(self, body: str | bytes = "", status: int = 200,
                 headers: dict[str, str] | None = None):
        self.body = body
        self.status = status
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}


def _handler(routes: dict[str, Route], origin_box: list[str]):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            route = routes.get(self.path) or Route("<p>missing</p>", status=404)
            body = route.body
            if isinstance(body, str):
                body = body.replace("{origin}", origin_box[0]).encode("utf-8")
            self.send_response(route.status)
            for name, value in route.headers.items():
                self.send_header(name, value.replace("{origin}", origin_box[0]))
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


@pytest.fixture
def serve():
    """Start a server for a routes dict and return its origin."""
    servers = []

    def start(routes: dict[str, Route]) -> str:
        origin_box = [""]
        httpd = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), _handler(routes, origin_box)
        )
        origin_box[0] = f"http://127.0.0.1:{httpd.server_address[1]}"
        threading.Thread(
            target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        ).start()
        servers.append(httpd)
        return origin_box[0]

    yield start
    for httpd in servers:
        httpd.shutdown()
