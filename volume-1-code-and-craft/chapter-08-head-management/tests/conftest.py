"""Shared fixtures: load the hyphenated scripts as modules, and serve
pages from a local HTTP server so no test touches the network."""

from __future__ import annotations

import http.server
import importlib.util
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

CHAPTER = Path(__file__).resolve().parent.parent


def load_script(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, CHAPTER / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@dataclass
class Route:
    status: int = 200
    body: str | bytes = ""
    headers: list[tuple[str, str]] = field(default_factory=list)
    # Status to answer HEAD with, when it differs from GET.
    head_status: int | None = None


class Site:
    def __init__(self, base: str):
        self.base = base
        self.routes: dict[str, Route] = {}

    def url(self, path: str) -> str:
        return self.base + path

    def add(self, path: str, body: str | bytes = "", status: int = 200, **kw) -> str:
        self.routes[path] = Route(status=status, body=body, **kw)
        return self.url(path)

    def redirect(self, path: str, location: str, status: int = 301) -> str:
        return self.add(path, status=status, headers=[("Location", location)])


@pytest.fixture
def site():
    holder: dict[str, Site] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _respond(self, send_body: bool):
            route = holder["site"].routes.get(self.path, Route(404, "<h1>404</h1>"))
            status = route.status
            if self.command == "HEAD" and route.head_status is not None:
                status = route.head_status
            body = route.body.encode() if isinstance(route.body, str) else route.body
            self.send_response(status)
            if not any(k.lower() == "content-type" for k, _ in route.headers):
                self.send_header("Content-Type", "text/html; charset=utf-8")
            for key, value in route.headers:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def do_GET(self):
            self._respond(True)

        def do_HEAD(self):
            self._respond(False)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    holder["site"] = Site(f"http://127.0.0.1:{httpd.server_address[1]}")
    threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield holder["site"]
    httpd.shutdown()
    httpd.server_close()
