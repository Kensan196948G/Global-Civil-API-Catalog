from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DESIGN_HTML_PATH = Path(__file__).resolve().parent / "Global Civil API Catalog.html"
DATA_DIR = ROOT / "data"
EXPORT_DIR = ROOT / "export"

# CSP allows Leaflet (unpkg.com), Google Fonts, and HTTPS tile images for the map UI.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://unpkg.com; "
    "style-src 'self' https://unpkg.com https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'"
)

# Paths forwarded to the FastAPI process (web/api_v1.py). Keeping the browser
# on a single origin means the CSP connect-src 'self', the SameSite session
# cookie and the api_v1 Origin check all hold without any CORS relaxation.
_PROXY_PREFIXES = ("/api/v1/", "/auth/")

# RFC 9110 hop-by-hop headers must not be forwarded in either direction.
# date/server are stripped from upstream responses because BaseHTTPRequestHandler
# emits its own copies and duplicates would be ambiguous.
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def api_upstream() -> tuple[str, str, int]:
    """Return (scheme, host, port) of the api_v1 process from env config."""
    raw = os.environ.get("CATALOG_API_UPSTREAM", "http://127.0.0.1:49232")
    parsed = urlparse(raw)
    scheme = parsed.scheme or "http"
    port = parsed.port or (443 if scheme == "https" else 80)
    return scheme, parsed.hostname or "127.0.0.1", port


_json_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_json_cached(path: Path) -> Any:
    """Return parsed JSON, re-reading only when the file's mtime changes."""
    key = str(path)
    mtime = path.stat().st_mtime
    with _cache_lock:
        if key in _json_cache and _json_cache[key][0] == mtime:
            return _json_cache[key][1]
    data = load_json(path)
    with _cache_lock:
        _json_cache[key] = (mtime, data)
    return data


def filter_catalog(
    catalog: list[dict],
    keyword: str = "",
    category: str = "",
    status: str = "",
) -> list[dict]:
    """Return catalog items matching all supplied filters."""
    if keyword:
        catalog = [
            item for item in catalog if keyword in json.dumps(item, ensure_ascii=False).lower()
        ]
    if category:
        catalog = [item for item in catalog if item["category"] == category]
    if status:
        catalog = [item for item in catalog if item["connection_status"] == status]
    return catalog


def latest_verification(results: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in sorted(results, key=lambda item: item["verified_at"]):
        latest[row["api_id"]] = row
    return latest


def status_counts(catalog: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in catalog:
        status = item.get("connection_status", "未設定")
        counts[status] = counts.get(status, 0) + 1
    return counts


def category_counts(catalog: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in catalog:
        category = item.get("category", "未設定")
        counts[category] = counts.get(category, 0) + 1
    return counts


def live_map_payload(catalog: list[dict], results: list[dict]) -> dict:
    latest = latest_verification(results)
    anchors = {
        "JP": (36.2, 138.2),
        "US": (39.5, -98.35),
        "Global": (8.0, 15.0),
    }
    offsets = [
        (0.0, 0.0),
        (1.2, 1.1),
        (-1.0, 1.5),
        (1.4, -1.1),
        (-1.3, -1.0),
        (2.1, 0.4),
        (-2.0, 0.2),
    ]
    features = []
    layers = []
    for index, item in enumerate(catalog):
        lat, lon = anchors.get(item.get("region") or "", (20.0, 0.0))
        lat_offset, lon_offset = offsets[index % len(offsets)]
        verification = latest.get(item["id"], {})
        features.append(
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "provider": item["provider"],
                "region": item["region"],
                "lat": round(lat + lat_offset + (index % 5) * 0.08, 5),
                "lon": round(lon + lon_offset + (index % 6) * 0.08, 5),
                "connection_status": item["connection_status"],
                "trust_rank": item["trust_rank"],
                "connection_priority": item["connection_priority"],
                "usage_summary": item.get("usage_summary", ""),
                "latest_verification": verification.get("result", "未検証"),
                "sample_endpoint": item.get("sample_endpoint", ""),
                "official_url": item.get("official_url", ""),
            }
        )
        endpoint = item.get("endpoint_template", "")
        formats = {str(fmt).lower() for fmt in item.get("data_formats", [])}
        if "{z}" in endpoint and "{x}" in endpoint and "{y}" in endpoint:
            layers.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "category": item["category"],
                    "provider": item["provider"],
                    "tile_url": endpoint,
                    "attribution": item.get("license_note", ""),
                    "enabled": item["connection_status"]
                    in {"実装接続済", "本格利用候補", "接続検証済"},
                    "is_tile": bool(formats & {"xyz tile", "png", "jpeg"}),
                }
            )
    return {
        "center": {"lat": 36.2, "lon": 138.2, "zoom": 5},
        "features": features,
        "layers": layers,
    }


class CatalogHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature.
        # Under pythonw.exe sys.stderr is None and the default implementation
        # would crash every request handler thread.
        if sys.stderr is not None:
            super().log_message(format, *args)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        self.send_header("Content-Security-Policy", _CSP)
        super().end_headers()

    def write_json(self, payload, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def is_proxied_path(self) -> bool:
        return urlparse(self.path).path.startswith(_PROXY_PREFIXES)

    def proxy_api(self) -> None:
        """Forward the request to the api_v1 (FastAPI) process unchanged.

        Redirects (e.g. /auth/login -> Entra ID) are passed through, never
        followed. Set-Cookie headers are relayed one-by-one so the session
        cookie survives. When the upstream is down the UI receives a JSON 503
        and the read-only catalog keeps working untouched.
        """
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        scheme, host, port = api_upstream()
        conn_cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(host, port, timeout=30)
        request_headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in _HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        try:
            conn.request(self.command, self.path, body=body, headers=request_headers)
            response = conn.getresponse()
            payload = response.read()
        except (OSError, http.client.HTTPException):
            self.write_json({"detail": "catalog editing service is unavailable"}, status=503)
            return
        finally:
            conn.close()
        self.send_response(response.status)
        for key, value in response.getheaders():
            if key.lower() in _HOP_BY_HOP_HEADERS or key.lower() in {
                "content-length",
                "date",
                "server",
            }:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler method name.
        if self.is_proxied_path():
            self.proxy_api()
            return
        self.send_error(404)

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler method name.
        if self.is_proxied_path():
            self.proxy_api()
            return
        self.send_error(404)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler method name.
        if self.is_proxied_path():
            self.proxy_api()
            return
        self.send_error(404)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        parsed = urlparse(self.path)
        if self.is_proxied_path():
            self.proxy_api()
            return
        if parsed.path in {"/design.html", "/claude-design.html"} and DESIGN_HTML_PATH.exists():
            self.handle_design_html(include_body=True)
            return
        if parsed.path == "/api/health":
            self.write_json({"status": "ok"})
            return
        if parsed.path == "/api/catalog":
            self.handle_catalog(parse_qs(parsed.query))
            return
        if parsed.path == "/api/verification":
            self.write_json(load_json_cached(DATA_DIR / "verification_results.json"))
            return
        if parsed.path == "/api/summary":
            self.handle_summary()
            return
        if parsed.path == "/api/metadata":
            self.write_json(load_json_cached(DATA_DIR / "catalog_metadata.json"))
            return
        if parsed.path == "/api/live-map":
            self.handle_live_map()
            return
        if parsed.path == "/api/export":
            self.handle_export_index()
            return
        if parsed.path.startswith("/exports/"):
            self.handle_export_file(parsed.path, parse_qs(parsed.query), include_body=True)
            return
        if parsed.path.startswith("/data/"):
            self.handle_data_file(parsed.path)
            return
        super().do_GET()

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler method name.
        parsed = urlparse(self.path)
        if self.is_proxied_path():
            self.proxy_api()
            return
        if parsed.path in {"/design.html", "/claude-design.html"} and DESIGN_HTML_PATH.exists():
            self.handle_design_html(include_body=False)
            return
        if parsed.path.startswith("/exports/"):
            self.handle_export_file(parsed.path, parse_qs(parsed.query), include_body=False)
            return
        super().do_HEAD()

    def handle_design_html(self, include_body: bool) -> None:
        data = DESIGN_HTML_PATH.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if include_body:
            self.wfile.write(data)

    def handle_catalog(self, query: dict[str, list[str]]) -> None:
        catalog = load_json_cached(DATA_DIR / "api_catalog.json")
        keyword = (query.get("q", [""])[0] or "").lower()
        category = query.get("category", [""])[0]
        status = query.get("status", [""])[0]
        self.write_json(filter_catalog(catalog, keyword=keyword, category=category, status=status))

    def handle_summary(self) -> None:
        catalog = load_json_cached(DATA_DIR / "api_catalog.json")
        results = load_json_cached(DATA_DIR / "verification_results.json")
        latest = latest_verification(results)
        summary = {
            "catalog_count": len(catalog),
            "verification_count": len(results),
            "candidate_count": len(
                [item for item in catalog if item["connection_status"] == "本格利用候補"]
            ),
            "implemented_count": len(
                [
                    item
                    for item in catalog
                    if item["connection_status"] in {"実装接続済", "本格利用候補"}
                ]
            ),
            "categories": sorted({item["category"] for item in catalog}),
            "statuses": sorted({item["connection_status"] for item in catalog}),
            "category_counts": category_counts(catalog),
            "status_counts": status_counts(catalog),
            "latest_verification": latest,
        }
        self.write_json(summary)

    def handle_live_map(self) -> None:
        catalog = load_json_cached(DATA_DIR / "api_catalog.json")
        results = load_json_cached(DATA_DIR / "verification_results.json")
        self.write_json(live_map_payload(catalog, results))

    def handle_export_index(self) -> None:
        exports = []
        for path in sorted(EXPORT_DIR.glob("*")):
            if path.is_file():
                exports.append(
                    {
                        "name": path.name,
                        "url": f"/exports/{quote(path.name)}",
                        "download_url": f"/exports/{quote(path.name)}?download=1",
                    }
                )
        self.write_json(exports)

    def handle_data_file(self, request_path: str) -> None:
        # Serves canonical data files (api_catalog.json, verification_results.json,
        # catalog_metadata.json) so the design bundle can fetch live data instead of
        # relying on its embedded copies.
        filename = unquote(request_path.removeprefix("/data/"))
        path = (DATA_DIR / filename).resolve()
        if not path.is_relative_to(DATA_DIR.resolve()) or not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_export_file(
        self,
        request_path: str,
        query: dict[str, list[str]],
        include_body: bool,
    ) -> None:
        filename = unquote(request_path.removeprefix("/exports/"))
        path = (EXPORT_DIR / filename).resolve()
        if not path.is_relative_to(EXPORT_DIR.resolve()) or not path.exists():
            self.send_error(404)
            return
        content_type = (
            "text/markdown; charset=utf-8" if path.suffix == ".md" else "text/plain; charset=utf-8"
        )
        if path.suffix == ".json":
            content_type = "application/json; charset=utf-8"
        if path.suffix == ".csv":
            content_type = "text/csv; charset=utf-8"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if query.get("download", ["0"])[0] == "1":
            encoded_name = quote(path.name)
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{encoded_name}",
            )
        self.end_headers()
        if include_body:
            self.wfile.write(data)


def find_free_port(host: str) -> int:
    """Return an OS-assigned free port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def resolve_port(host: str, port: int, auto_port: bool) -> int:
    """Return a usable port for host.

    Binds to the requested port (without SO_REUSEADDR, for an accurate check).
    When the port is free it is returned as-is. When it is in use and
    auto_port is True a free port is returned instead; otherwise the OSError
    from the failed bind is propagated.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, port))
        return port
    except OSError:
        if auto_port:
            return find_free_port(host)
        raise


def detect_lan_ip() -> str:
    """Return the primary LAN IP address, or 127.0.0.1 when unavailable."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


LOOPBACK_HOSTS = {"localhost", "::1"}


def is_loopback_host(host: str) -> bool:
    """True for bind addresses that only resolve locally (localhost, ::1, 127/8)."""
    return host in LOOPBACK_HOSTS or host.startswith("127.")


def format_startup_banner(host: str, port: int, lan_ip: str) -> str:
    """Startup banner; the LAN URL is only advertised when the bind interface
    is actually reachable from other machines (a loopback bind is not)."""
    base = f"Global Civil API Catalog WebUI listening on {host}:{port}"
    if is_loopback_host(host):
        url_host = "[::1]" if host == "::1" else host
        return f"{base} (local access only: http://{url_host}:{port})"
    return f"{base} (LAN: http://{lan_ip}:{port})"


def write_port_lock(path: str, port: int) -> None:
    """Write the resolved port number to path as a single line of text."""
    Path(path).write_text(f"{port}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global Civil API Catalog WebUI server")
    parser.add_argument(
        "--host",
        default=os.environ.get("CATALOG_HOST", "127.0.0.1"),
        help="host interface to bind (default: env CATALOG_HOST or 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("CATALOG_PORT", "8080")),
        help="port to listen on (default: env CATALOG_PORT or 8080)",
    )
    parser.add_argument(
        "--auto-port",
        action="store_true",
        help="fall back to a free port when the requested port is in use",
    )
    parser.add_argument(
        "--port-lock-file",
        default=None,
        help="path to write the resolved port number to",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    port = resolve_port(args.host, args.port, args.auto_port)
    server = ThreadingHTTPServer((args.host, port), CatalogHandler)
    # Written only after the server actually holds the port, so the lock
    # file can never advertise a port the server failed to bind.
    if args.port_lock_file:
        write_port_lock(args.port_lock_file, port)
    print(format_startup_banner(args.host, port, detect_lan_ip()), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
