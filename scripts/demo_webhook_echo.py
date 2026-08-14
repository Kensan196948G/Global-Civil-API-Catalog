"""Minimal webhook echo server for the MVP demo environment (stdlib only).

Listens on 127.0.0.1:49339 and appends every POST to
``data/demo/webhook_deliveries.jsonl`` so the demo shows real deliveries.

Usage: python scripts/demo_webhook_echo.py [--port 49339]
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "demo" / "webhook_deliveries.jsonl"


class EchoHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib.
        pass

    def _record(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "event": self.headers.get("X-Catalog-Webhook-Event", ""),
            "delivery_id": self.headers.get("X-Catalog-Delivery", ""),
            "signature": self.headers.get("X-Catalog-Signature", ""),
            "body": body.decode("utf-8", errors="replace"),
        }
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        payload = json.dumps({"ok": True, "delivery_id": record["delivery_id"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 - stdlib.
        self._record()

    def do_GET(self) -> None:  # noqa: N802 - stdlib.
        payload = b'{"status":"ok","endpoint":"/webhook-echo"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=49339)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), EchoHandler)
    print(f"Demo webhook echo listening on 127.0.0.1:{args.port} (log: {LOG_PATH})", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
