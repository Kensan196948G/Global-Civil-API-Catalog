from __future__ import annotations

import csv
import json
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / os.environ.get("CATALOG_DATA_DIR", "data")
EXPORT_DIR = ROOT / os.environ.get("CATALOG_EXPORT_DIR", "export")

CATALOG_PATH = DATA_DIR / "api_catalog.json"
CATALOG_METADATA_PATH = DATA_DIR / "catalog_metadata.json"
VERIFICATION_PATH = DATA_DIR / "verification_results.json"
# Time-series history (issue #49): verification_results.json above stays a
# point-in-time snapshot that is overwritten on every run; this JSON Lines
# file (one `build_result` record per line) accumulates history across runs
# so anomaly detection has a prior baseline to compare against. This is a
# deliberate interim JSON-based store for the pre-#46 (DB migration) period;
# see docs/verification-plan.md for the DB fast-follow plan.
VERIFICATION_HISTORY_PATH = DATA_DIR / "verification_history.jsonl"
# Retention window applied on every append so the file does not grow
# unbounded. At the current weekly cadence and catalog size this keeps the
# file well under a few hundred KB, so a full-file rewrite on each append
# (rather than true O(1) appends) is simple and cheap enough.
VERIFICATION_HISTORY_RETENTION_DAYS = 90

REQUIRED_CATALOG_FIELDS = {
    "id",
    "name",
    "category",
    "provider",
    "region",
    "official_url",
    "data_formats",
    "api_key_required",
    "auth_type",
    "license_note",
    "commercial_use",
    "last_checked_at",
    "connection_status",
    "trust_rank",
    "connection_priority",
    "business_fit_score",
    "integration_score",
    "usage_summary",
    "usage_notes",
    "tags",
}

REQUIRED_VERIFICATION_FIELDS = {
    "id",
    "api_id",
    "verified_at",
    "result",
    "sample_request_path",
    "sample_response_path",
}

API_KEY_VALUES = {"required", "not_required", "unknown"}
AUTH_VALUES = {"none", "api_key", "oauth2", "other", "unknown"}
COMMERCIAL_USE_VALUES = {"allowed", "restricted", "unknown"}
STATUS_VALUES = {
    "未調査",
    "調査中",
    "接続候補",
    "接続検証済",
    "実装接続済",
    "本格利用候補",
    "保留",
    "除外",
    "利用終了",
}
TRUST_RANK_VALUES = {"A", "B", "C", "D", "E"}
VERIFICATION_RESULT_VALUES = {"success", "warning", "failure", "skipped"}


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def load_catalog(path: Path = CATALOG_PATH) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("catalog root must be a list")
    return data


def load_verification_results(path: Path = VERIFICATION_PATH) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("verification root must be a list")
    return data


def load_verification_history(path: Path = VERIFICATION_HISTORY_PATH) -> list[dict[str, Any]]:
    """Read the newline-delimited verification history file.

    Returns an empty list when the file does not exist yet (e.g. before the
    first `--append-history` run) instead of raising, so callers such as the
    anomaly detector can treat "no history" as a normal first-run state.
    Blank lines are skipped so the file tolerates manual edits/trimming.
    """
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _verified_at_is_within_retention(record: dict[str, Any], cutoff: datetime) -> bool:
    verified_at = record.get("verified_at")
    if not isinstance(verified_at, str):
        # Keep malformed/legacy records rather than silently losing data;
        # they simply won't sort meaningfully for anomaly comparisons.
        return True
    try:
        parsed = datetime.fromisoformat(verified_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed >= cutoff


def append_verification_history(
    new_records: list[dict[str, Any]],
    path: Path = VERIFICATION_HISTORY_PATH,
    retention_days: int = VERIFICATION_HISTORY_RETENTION_DAYS,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Append `new_records` to the JSONL history file, pruning entries older
    than `retention_days` (based on `verified_at`). Rewrites the whole file
    on each call rather than doing a literal filesystem append, which keeps
    the retention/pruning logic simple; see the module-level comment on
    VERIFICATION_HISTORY_PATH for why this is cheap enough in practice.

    Returns the resulting (pruned + appended) record list.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)
    existing = load_verification_history(path)
    kept = [record for record in existing if _verified_at_is_within_retention(record, cutoff)]
    kept.extend(new_records)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for record in kept:
            file.write(json.dumps(record, ensure_ascii=False))
            file.write("\n")
    return kept


def load_catalog_metadata(path: Path = CATALOG_METADATA_PATH) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError("catalog metadata root must be an object")
    return data


def validate_date(value: str) -> None:
    date.fromisoformat(value)


def validate_datetime(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_catalog(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    ids: list[str] = []

    for index, item in enumerate(records, start=1):
        missing = REQUIRED_CATALOG_FIELDS - item.keys()
        if missing:
            errors.append(f"catalog[{index}] missing fields: {', '.join(sorted(missing))}")

        api_id = item.get("id")
        if not isinstance(api_id, str) or not api_id:
            errors.append(f"catalog[{index}] id must be a non-empty string")
        else:
            ids.append(api_id)

        if item.get("api_key_required") not in API_KEY_VALUES:
            errors.append(f"{api_id}: invalid api_key_required")
        if item.get("auth_type") not in AUTH_VALUES:
            errors.append(f"{api_id}: invalid auth_type")
        if item.get("commercial_use") not in COMMERCIAL_USE_VALUES:
            errors.append(f"{api_id}: invalid commercial_use")
        if item.get("connection_status") not in STATUS_VALUES:
            errors.append(f"{api_id}: invalid connection_status")
        if item.get("trust_rank") not in TRUST_RANK_VALUES:
            errors.append(f"{api_id}: invalid trust_rank")

        priority = item.get("connection_priority")
        if not isinstance(priority, int) or not 1 <= priority <= 5:
            errors.append(f"{api_id}: connection_priority must be 1-5")

        for field in ("business_fit_score", "integration_score"):
            score = item.get(field)
            if not isinstance(score, int) or not 0 <= score <= 100:
                errors.append(f"{api_id}: {field} must be 0-100")

        if not isinstance(item.get("data_formats"), list) or not item.get("data_formats"):
            errors.append(f"{api_id}: data_formats must be a non-empty list")
        if not isinstance(item.get("tags"), list):
            errors.append(f"{api_id}: tags must be a list")

        try:
            validate_date(str(item.get("last_checked_at")))
        except ValueError:
            errors.append(f"{api_id}: last_checked_at must be YYYY-MM-DD")

    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    for api_id in duplicates:
        errors.append(f"duplicate catalog id: {api_id}")

    return errors


def validate_verification_results(
    records: list[dict[str, Any]], catalog_records: list[dict[str, Any]]
) -> list[str]:
    errors: list[str] = []
    catalog_ids = {item["id"] for item in catalog_records}
    ids: list[str] = []

    for index, item in enumerate(records, start=1):
        missing = REQUIRED_VERIFICATION_FIELDS - item.keys()
        if missing:
            errors.append(f"verification[{index}] missing fields: {', '.join(sorted(missing))}")

        result_id = item.get("id")
        if isinstance(result_id, str):
            ids.append(result_id)

        api_id = item.get("api_id")
        if api_id not in catalog_ids:
            errors.append(f"{result_id}: api_id does not exist in catalog: {api_id}")
        if item.get("result") not in VERIFICATION_RESULT_VALUES:
            errors.append(f"{result_id}: invalid result")

        try:
            validate_datetime(str(item.get("verified_at")))
        except ValueError:
            errors.append(f"{result_id}: verified_at must be ISO datetime")

    duplicates = [item for item, count in Counter(ids).items() if count > 1]
    for result_id in duplicates:
        errors.append(f"duplicate verification id: {result_id}")

    return errors


def trust_score(item: dict[str, Any], verification_by_api: dict[str, dict[str, Any]]) -> int:
    score = 0
    if item.get("provider_type") in {"government", "international", "official", "foundation"}:
        score += 30
    if item.get("document_url"):
        score += 20
    if item.get("license_note") and item.get("commercial_use") != "unknown":
        score += 20
    if item.get("update_frequency"):
        score += 10
    if item.get("data_formats"):
        score += 10
    if verification_by_api.get(item["id"], {}).get("result") == "success":
        score += 10
    return min(score, 100)


def trust_rank(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    if score >= 30:
        return "D"
    return "E"


def priority_score(item: dict[str, Any], computed_trust_score: int) -> float:
    target_projects = item.get("target_projects") or []
    project_score = min(len(target_projects) * 25, 100)
    return (
        computed_trust_score * 0.30
        + item["business_fit_score"] * 0.35
        + item["integration_score"] * 0.20
        + project_score * 0.15
    )


def priority_rank(score: float) -> int:
    if score >= 85:
        return 5
    if score >= 70:
        return 4
    if score >= 55:
        return 3
    if score >= 40:
        return 2
    return 1


def latest_verification_by_api(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in sorted(records, key=lambda row: row["verified_at"]):
        latest[item["api_id"]] = item
    return latest


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
