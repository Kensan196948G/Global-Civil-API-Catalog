from scripts.detect_verification_anomalies import (
    ANOMALY_RECORD_COUNT_CHANGE,
    ANOMALY_RESPONSE_TIME_DEGRADED,
    ANOMALY_RESULT_REGRESSION,
    detect_anomalies,
)


def _result(**overrides: object) -> dict:
    base = {
        "api_id": "TEST-API-001",
        "verified_at": "2026-09-01T00:00:00+00:00",
        "result": "success",
        "response_time_ms": 100,
        "record_count": 10,
    }
    base.update(overrides)
    return base


def test_no_history_first_run_returns_no_anomalies_and_does_not_crash() -> None:
    current = [_result()]
    assert detect_anomalies(current, {}) == []


def test_no_anomalies_when_nothing_changed_meaningfully() -> None:
    previous_by_api = {"TEST-API-001": _result(response_time_ms=110, record_count=11)}
    current = [_result(response_time_ms=120, record_count=12)]
    assert detect_anomalies(current, previous_by_api) == []


def test_result_regression_success_to_failure() -> None:
    previous_by_api = {"TEST-API-001": _result(result="success")}
    current = [_result(result="failure", note="live verification executed")]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["type"] == ANOMALY_RESULT_REGRESSION
    assert anomalies[0]["api_id"] == "TEST-API-001"
    assert anomalies[0]["previous_result"] == "success"
    assert anomalies[0]["current_result"] == "failure"


def test_result_regression_success_to_warning() -> None:
    previous_by_api = {"TEST-API-001": _result(result="success")}
    current = [_result(result="warning")]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["type"] == ANOMALY_RESULT_REGRESSION


def test_result_regression_not_flagged_when_previous_already_failing() -> None:
    previous_by_api = {"TEST-API-001": _result(result="failure")}
    current = [_result(result="failure")]

    assert detect_anomalies(current, previous_by_api) == []


def test_response_time_degraded_by_ratio() -> None:
    previous_by_api = {"TEST-API-001": _result(response_time_ms=100)}
    current = [_result(response_time_ms=250)]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["type"] == ANOMALY_RESPONSE_TIME_DEGRADED
    assert anomalies[0]["previous_response_time_ms"] == 100
    assert anomalies[0]["current_response_time_ms"] == 250


def test_response_time_degraded_by_absolute_threshold_even_with_small_ratio() -> None:
    previous_by_api = {"TEST-API-001": _result(response_time_ms=2000)}
    current = [_result(response_time_ms=5200)]

    anomalies = detect_anomalies(current, previous_by_api)

    assert any(a["type"] == ANOMALY_RESPONSE_TIME_DEGRADED for a in anomalies)


def test_response_time_not_flagged_for_small_absolute_change() -> None:
    previous_by_api = {"TEST-API-001": _result(response_time_ms=10)}
    current = [_result(response_time_ms=15)]

    assert detect_anomalies(current, previous_by_api) == []


def test_record_count_change_increase_flagged() -> None:
    previous_by_api = {"TEST-API-001": _result(record_count=100)}
    current = [_result(record_count=160)]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["type"] == ANOMALY_RECORD_COUNT_CHANGE
    assert anomalies[0]["previous_record_count"] == 100
    assert anomalies[0]["current_record_count"] == 160


def test_record_count_change_decrease_flagged() -> None:
    previous_by_api = {"TEST-API-001": _result(record_count=100)}
    current = [_result(record_count=40)]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["type"] == ANOMALY_RECORD_COUNT_CHANGE


def test_record_count_none_values_do_not_crash_or_flag() -> None:
    previous_by_api = {"TEST-API-001": _result(record_count=None)}
    current = [_result(record_count=None)]

    assert detect_anomalies(current, previous_by_api) == []


def test_multiple_anomaly_types_detected_for_same_api() -> None:
    previous_by_api = {
        "TEST-API-001": _result(result="success", response_time_ms=100, record_count=100)
    }
    current = [_result(result="failure", response_time_ms=5000, record_count=10)]

    anomalies = detect_anomalies(current, previous_by_api)

    types = {a["type"] for a in anomalies}
    assert types == {
        ANOMALY_RESULT_REGRESSION,
        ANOMALY_RESPONSE_TIME_DEGRADED,
        ANOMALY_RECORD_COUNT_CHANGE,
    }


def test_unknown_api_id_in_current_is_skipped() -> None:
    current = [_result(api_id="NEW-API-999")]
    assert detect_anomalies(current, {}) == []


def test_multiple_current_results_only_flag_the_ones_that_regressed() -> None:
    previous_by_api = {
        "API-A": _result(api_id="API-A", result="success"),
        "API-B": _result(api_id="API-B", result="success"),
    }
    current = [
        _result(api_id="API-A", result="success"),
        _result(api_id="API-B", result="failure"),
    ]

    anomalies = detect_anomalies(current, previous_by_api)

    assert len(anomalies) == 1
    assert anomalies[0]["api_id"] == "API-B"
