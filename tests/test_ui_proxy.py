"""Reverse-proxy tests: /api/v1/* and /auth/* forwarded to the api_v1 process.

The static server (web/server.py) and the FastAPI process (web/api_v1.py) are
separate processes on separate ports; the proxy keeps the browser on a single
origin so CSP connect-src 'self', the SameSite session cookie and the api_v1
Origin check all hold. These tests run a stub upstream plus a real
CatalogHandler server on ephemeral ports — no FastAPI or database required.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from web.server import CatalogHandler


class StubUpstreamHandler(BaseHTTPRequestHandler):
    """Echoes request facts back as JSON; /auth/login answers with a redirect."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature.
        pass

    def _echo(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        payload = json.dumps(
            {
                "method": self.command,
                "path": self.path,
                "origin": self.headers.get("Origin"),
                "cookie": self.headers.get("Cookie"),
                "x_forwarded_for": self.headers.get("X-Forwarded-For"),
                "body": body.decode("utf-8"),
            }
        ).encode("utf-8")
        self.send_response(201 if self.command == "POST" else 200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Set-Cookie", "first=1; Path=/")
        self.send_header("Set-Cookie", "second=2; Path=/")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        if self.path == "/auth/login":
            self.send_response(302)
            self.send_header("Location", "https://login.example/authorize")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._echo()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._echo()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._echo()

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._echo()

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler method name.
        self._echo()


def _serve(server: ThreadingHTTPServer) -> None:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


@pytest.fixture(scope="module")
def upstream_port():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubUpstreamHandler)
    _serve(server)
    yield server.server_port
    server.shutdown()


@pytest.fixture(scope="module")
def ui_port(upstream_port):
    previous = os.environ.get("CATALOG_API_UPSTREAM")
    os.environ["CATALOG_API_UPSTREAM"] = f"http://127.0.0.1:{upstream_port}"
    server = ThreadingHTTPServer(("127.0.0.1", 0), CatalogHandler)
    _serve(server)
    yield server.server_port
    server.shutdown()
    if previous is None:
        os.environ.pop("CATALOG_API_UPSTREAM", None)
    else:
        os.environ["CATALOG_API_UPSTREAM"] = previous


def request(port: int, method: str, path: str, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response, data


def test_get_auth_me_is_proxied_with_cookie(ui_port) -> None:
    response, data = request(ui_port, "GET", "/auth/me", headers={"Cookie": "catalog_session=abc"})
    echo = json.loads(data)

    assert response.status == 200
    assert echo["path"] == "/auth/me"
    assert echo["cookie"] == "catalog_session=abc"
    assert echo["x_forwarded_for"] == "127.0.0.1"


def test_post_api_v1_forwards_body_and_origin(ui_port) -> None:
    body = json.dumps({"action": "submit", "reason": "ready for review"})
    response, data = request(
        ui_port,
        "POST",
        "/api/v1/entries/GSI-TILE-STD-001/transitions",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": "http://localhost:49232",
        },
    )
    echo = json.loads(data)

    assert response.status == 201  # upstream status passes through untouched
    assert echo["method"] == "POST"
    assert echo["body"] == body
    assert echo["origin"] == "http://localhost:49232"


def test_delete_query_string_passes_through(ui_port) -> None:
    response, data = request(
        ui_port, "DELETE", "/api/v1/entries/OLD-API-001?reason=duplicate%20entry"
    )
    echo = json.loads(data)

    assert response.status == 200
    assert echo["path"] == "/api/v1/entries/OLD-API-001?reason=duplicate%20entry"


def test_patch_is_proxied(ui_port) -> None:
    body = json.dumps({"reason": "fix name", "name": "New name"})
    response, data = request(
        ui_port,
        "PATCH",
        "/api/v1/entries/GSI-TILE-STD-001",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    echo = json.loads(data)

    assert response.status == 200
    assert echo["method"] == "PATCH"
    assert echo["body"] == body


def test_auth_redirect_is_passed_through_not_followed(ui_port) -> None:
    response, _ = request(ui_port, "GET", "/auth/login")

    assert response.status == 302
    assert response.getheader("Location") == "https://login.example/authorize"


def test_duplicate_set_cookie_headers_survive(ui_port) -> None:
    response, _ = request(ui_port, "GET", "/auth/me")
    cookies = response.msg.get_all("Set-Cookie")

    assert cookies == ["first=1; Path=/", "second=2; Path=/"]


def test_upstream_down_returns_json_503(ui_port, monkeypatch) -> None:
    # Reserve a port and close it so nothing is listening there.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
    monkeypatch.setenv("CATALOG_API_UPSTREAM", f"http://127.0.0.1:{closed_port}")

    response, data = request(ui_port, "GET", "/api/v1/entries")

    assert response.status == 503
    assert json.loads(data) == {"detail": "catalog editing service is unavailable"}


def test_non_proxied_api_paths_stay_local(ui_port) -> None:
    response, data = request(ui_port, "GET", "/api/health")

    assert response.status == 200
    assert json.loads(data) == {"status": "ok"}


def test_security_headers_are_present(ui_port) -> None:
    response, _ = request(ui_port, "GET", "/api/health")

    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert "geolocation=()" in response.getheader("Permissions-Policy", "")
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in response.getheader("Content-Security-Policy", "")


def test_head_is_proxied_without_body(ui_port) -> None:
    response, data = request(ui_port, "HEAD", "/api/v1/entries")

    assert response.status == 200
    assert data == b""
