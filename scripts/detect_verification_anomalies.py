"""Detect anomalies by comparing the latest verification run against history.

Part of issue #49 (定期品質検証の強化). This script is intentionally standalone
and filesystem-driven so it can run as its own step in
`.github/workflows/scheduled-verify.yml`, right after
`scripts/run_verification.py --live --write --append-history`:

    python scripts/run_verification.py --live --write --append-history --limit 50
    python scripts/detect_verification_anomalies.py --output data/verification_anomalies.json

`detect_anomalies()` is a pure function (no filesystem access) so it is fully
unit-testable; see tests/test_verification_anomalies.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.catalog_utils import (  # noqa: E402
    VERIFICATION_HISTORY_PATH,
    VERIFICATION_PATH,
    latest_verification_by_api,
    load_json,
    load_verification_history,
    write_json,
)

# response_time_ms is flagged as degraded when it is at least this many times
# the previous run's value...
RESPONSE_TIME_RATIO_THRESHOLD = 2.0
# ...or has grown by at least this many milliseconds in absolute terms
# (guards against e.g. 10ms -> 15ms passing the ratio check on tiny numbers,
# while still catching a fast API becoming a slow one).
RESPONSE_TIME_ABSOLUTE_THRESHOLD_MS = 3000
# record_count is flagged when it changes (either direction) by at least this
# fraction of the previous run's value.
RECORD_COUNT_CHANGE_RATIO_THRESHOLD = 0.5

ANOMALY_RESULT_REGRESSION = "result_regression"
ANOMALY_RESPONSE_TIME_DEGRADED = "response_time_degraded"
ANOMALY_RECORD_COUNT_CHANGE = "record_count_change"


def detect_anomalies(
    current_results: list[dict[str, Any]],
    previous_by_api: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare `current_results` (this run's `build_result` records) against
    `previous_by_api` (api_id -> most recent prior record, e.g. from
    `catalog_utils.latest_verification_by_api` over history strictly older
    than this run).

    Pure function: does not touch the filesystem, does not raise on missing
    history (an api_id absent from `previous_by_api` — including the common
    "first run ever" case where the map is empty — is simply skipped, not
    treated as an anomaly).
    """
    anomalies: list[dict[str, Any]] = []

    for current in current_results:
        api_id = current.get("api_id")
        previous = previous_by_api.get(api_id) if api_id else None
        if previous is None:
            continue

        if previous.get("result") == "success" and current.get("result") in (
            "failure",
            "warning",
        ):
            anomalies.append(
                {
                    "api_id": api_id,
                    "type": ANOMALY_RESULT_REGRESSION,
                    "message": (
                        f"{api_id}: result regressed from success to {current.get('result')}"
                    ),
                    "previous_result": previous.get("result"),
                    "current_result": current.get("result"),
                    "current_note": current.get("note") or current.get("error_message") or "",
                }
            )

        prev_rt = previous.get("response_time_ms")
        cur_rt = current.get("response_time_ms")
        if (
            isinstance(prev_rt, (int, float))
            and not isinstance(prev_rt, bool)
            and isinstance(cur_rt, (int, float))
            and not isinstance(cur_rt, bool)
            and prev_rt > 0
        ):
            degraded_ratio = cur_rt >= prev_rt * RESPONSE_TIME_RATIO_THRESHOLD
            degraded_absolute = (cur_rt - prev_rt) >= RESPONSE_TIME_ABSOLUTE_THRESHOLD_MS
            if degraded_ratio or degraded_absolute:
                anomalies.append(
                    {
                        "api_id": api_id,
                        "type": ANOMALY_RESPONSE_TIME_DEGRADED,
                        "message": (
                            f"{api_id}: response_time_ms degraded from {prev_rt} to {cur_rt}"
                        ),
                        "previous_response_time_ms": prev_rt,
                        "current_response_time_ms": cur_rt,
                    }
                )

        prev_rc = previous.get("record_count")
        cur_rc = current.get("record_count")
        if (
            isinstance(prev_rc, int)
            and not isinstance(prev_rc, bool)
            and isinstance(cur_rc, int)
            and not isinstance(cur_rc, bool)
            and prev_rc > 0
        ):
            change_ratio = abs(cur_rc - prev_rc) / prev_rc
            if change_ratio >= RECORD_COUNT_CHANGE_RATIO_THRESHOLD:
                anomalies.append(
                    {
                        "api_id": api_id,
                        "type": ANOMALY_RECORD_COUNT_CHANGE,
                        "message": f"{api_id}: record_count changed from {prev_rc} to {cur_rc}",
                        "previous_record_count": prev_rc,
                        "current_record_count": cur_rc,
                    }
                )

    return anomalies


def _previous_by_api_excluding_current(
    current_results: list[dict[str, Any]], history: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Build the api_id -> latest-record map from `history`, excluding any
    entries that are actually part of the current run (identified by the
    (api_id, verified_at) pair `build_result` assigns). This makes the CLI
    tolerant of running either before or after `--append-history` has
    written the current run into the same history file.
    """
    current_keys = {(r.get("api_id"), r.get("verified_at")) for r in current_results}
    previous_history = [
        h for h in history if (h.get("api_id"), h.get("verified_at")) not in current_keys
    ]
    if not previous_history:
        return {}
    return latest_verification_by_api(previous_history)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect anomalies (result regressions, response-time degradation, "
            "record_count swings) by comparing the latest verification results "
            "against data/verification_history.jsonl."
        )
    )
    parser.add_argument("--results", type=Path, default=VERIFICATION_PATH)
    parser.add_argument("--history", type=Path, default=VERIFICATION_HISTORY_PATH)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write detected anomalies as JSON to this path (always printed to stdout too)",
    )
    args = parser.parse_args()

    current_results = load_json(args.results) if args.results.exists() else []
    history = load_verification_history(args.history)
    previous_by_api = _previous_by_api_excluding_current(current_results, history)

    anomalies = detect_anomalies(current_results, previous_by_api)

    print(json.dumps(anomalies, ensure_ascii=False, indent=2))
    if args.output:
        write_json(args.output, anomalies)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
