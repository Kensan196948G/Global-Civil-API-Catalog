from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    CATALOG_PATH,
    VERIFICATION_PATH,
    load_catalog,
    write_json,
)


USER_AGENT = "Global-Civil-API-Catalog/0.1 (+https://github.com/Kensan196948G/Global-Civil-API-Catalog)"
# Saved response samples are capped at this size. response_size_bytes therefore
# records the captured (possibly truncated) sample size, not the full response
# length; samples that hit this cap are flagged as truncated in the note.
MAX_SAMPLE_BYTES = 64 * 1024


def request_url(url: str, timeout: int) -> tuple[int | None, bytes, int]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_SAMPLE_BYTES)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return response.status, body, elapsed_ms
    except urllib.error.HTTPError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return exc.code, exc.read(1024), elapsed_ms


def build_result(item: dict, live: bool, timeout: int) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result = {
        "id": f"VERIFY-{item['id']}-{now[:10].replace('-', '')}",
        "api_id": item["id"],
        "verified_at": now,
        "verified_by": "run_verification.py",
        "result": "skipped",
        "http_status": None,
        "response_time_ms": None,
        "response_size_bytes": None,
        "record_count": None,
        "sample_request_path": f"samples/requests/{item['id']}.txt",
        "sample_response_path": f"samples/responses/{item['id']}.sample",
        "error_message": "",
        "note": "offline mode; live request not executed",
    }

    endpoint = item.get("sample_endpoint") or item.get("endpoint_template")
    if endpoint:
        request_path = Path(result["sample_request_path"])
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(
            f'curl -L -H "User-Agent: Global-Civil-API-Catalog/0.1" "{endpoint}"\n',
            encoding="utf-8",
        )

    # Always ensure a response sample exists; the live path overwrites it with
    # the real payload when a request is made.
    response_path = Path(result["sample_response_path"])
    response_path.parent.mkdir(parents=True, exist_ok=True)
    if not response_path.exists():
        response_path.write_text(
            "no live response captured; see verification note\n", encoding="utf-8"
        )

    if not live:
        return result
    if item["api_key_required"] == "required":
        result["note"] = "API key required; skipped by default"
        return result
    if not endpoint or "{" in endpoint:
        result["result"] = "warning"
        result["note"] = "no concrete sample endpoint configured"
        return result

    try:
        status, body, elapsed_ms = request_url(endpoint, timeout)
        result["http_status"] = status
        result["response_time_ms"] = elapsed_ms
        result["response_size_bytes"] = len(body)
        result["result"] = "success" if status and 200 <= status < 300 else "failure"
        result["note"] = "live verification executed"
        if len(body) >= MAX_SAMPLE_BYTES:
            result["sample_truncated"] = True
            result["note"] += f"; sample truncated to {MAX_SAMPLE_BYTES // 1024}KB"
        sample_path = Path(result["sample_response_path"])
        sample_path.parent.mkdir(parents=True, exist_ok=True)
        sample_path.write_bytes(body)
    except Exception as exc:  # noqa: BLE001 - CLI result must record any connector failure.
        result["result"] = "failure"
        result["error_message"] = str(exc)
        result["note"] = "live verification failed"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run catalog verification checks.")
    parser.add_argument("--live", action="store_true", help="execute real HTTP requests")
    parser.add_argument("--limit", type=int, default=10, help="maximum records to verify")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout seconds")
    parser.add_argument("--write", action="store_true", help="write results to data/verification_results.json")
    args = parser.parse_args()

    catalog = load_catalog(CATALOG_PATH)
    candidates = [item for item in catalog if item["connection_status"] in {"接続候補", "接続検証済", "実装接続済", "本格利用候補"}]
    results = [build_result(item, args.live, args.timeout) for item in candidates[: args.limit]]

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if args.write:
        write_json(VERIFICATION_PATH, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
