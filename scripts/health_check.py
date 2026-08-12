"""Read-only health probe for the catalog Web UI and API/DB layers.

Usage:
    python scripts/health_check.py [BASE_URL]

Exits 0 when both /api/health and /api/v1/health report ok (the static
server reverse-proxies /api/v1/* to the FastAPI process, so a single base
URL covers both layers). Suitable for cron / systemd on-calendar checks.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def probe(base: str, path: str, timeout: int = 10) -> tuple[int | None, dict]:
    try:
        with urllib.request.urlopen(f"{base}{path}", timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - CLI must classify any failure.
        return None, {"error": type(exc).__name__}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:49231")
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")

    web_status, web_body = probe(base, "/api/health")
    api_status, api_body = probe(base, "/api/v1/health")

    web_ok = web_status == 200 and web_body.get("status") == "ok"
    api_ok = api_status == 200 and api_body.get("database") == "ok"

    print(f"web /api/health:      {web_status} {web_body}")
    print(f"api /api/v1/health:   {api_status} {api_body}")

    if web_ok and api_ok:
        print("HEALTH: OK")
        return 0
    print("HEALTH: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
