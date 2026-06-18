from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DESIGN_HTML_PATH = Path(__file__).resolve().parent / "Global Civil API Catalog.html"
DATA_DIR = ROOT / "data"
EXPORT_DIR = ROOT / "export"


def load_json(path: Path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)


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
        lat, lon = anchors.get(item.get("region"), (20.0, 0.0))
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
                    "enabled": item["connection_status"] in {"実装接続済", "本格利用候補", "接続検証済"},
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

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def write_json(self, payload, status: int = 200) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name.
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/design.html", "/claude-design.html"} and DESIGN_HTML_PATH.exists():
            self.handle_design_html(include_body=True)
            return
        if parsed.path == "/api/health":
            self.write_json({"status": "ok"})
            return
        if parsed.path == "/api/catalog":
            self.handle_catalog(parse_qs(parsed.query))
            return
        if parsed.path == "/api/verification":
            self.write_json(load_json(DATA_DIR / "verification_results.json"))
            return
        if parsed.path == "/api/summary":
            self.handle_summary()
            return
        if parsed.path == "/api/metadata":
            self.write_json(load_json(DATA_DIR / "catalog_metadata.json"))
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
        if parsed.path in {"/", "/index.html", "/design.html", "/claude-design.html"} and DESIGN_HTML_PATH.exists():
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
        catalog = load_json(DATA_DIR / "api_catalog.json")
        keyword = (query.get("q", [""])[0] or "").lower()
        category = query.get("category", [""])[0]
        status = query.get("status", [""])[0]

        if keyword:
            catalog = [
                item
                for item in catalog
                if keyword in json.dumps(item, ensure_ascii=False).lower()
            ]
        if category:
            catalog = [item for item in catalog if item["category"] == category]
        if status:
            catalog = [item for item in catalog if item["connection_status"] == status]

        self.write_json(catalog)

    def handle_summary(self) -> None:
        catalog = load_json(DATA_DIR / "api_catalog.json")
        results = load_json(DATA_DIR / "verification_results.json")
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
        catalog = load_json(DATA_DIR / "api_catalog.json")
        results = load_json(DATA_DIR / "verification_results.json")
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
        if not str(path).startswith(str(DATA_DIR.resolve())) or not path.exists():
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
        if not str(path).startswith(str(EXPORT_DIR.resolve())) or not path.exists():
            self.send_error(404)
            return
        content_type = "text/markdown; charset=utf-8" if path.suffix == ".md" else "text/plain; charset=utf-8"
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


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", 8080), CatalogHandler)
    print("Global Civil API Catalog WebUI listening on 0.0.0.0:8080", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
