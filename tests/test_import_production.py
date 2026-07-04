import pytest

from scripts.import_production_catalog import (
    check_verification_consistency,
    parse_args,
)


def test_keep_local_verification_flag_defaults_to_false() -> None:
    assert parse_args([]).keep_local_verification is False


def test_keep_local_verification_flag_parses() -> None:
    assert parse_args(["--keep-local-verification"]).keep_local_verification is True


def test_consistency_guard_raises_when_bundle_differs_and_flag_off() -> None:
    with pytest.raises(ValueError):
        check_verification_consistency(
            [{"id": "v1"}], [{"id": "v2"}], keep_local_verification=False
        )


def test_consistency_guard_passes_when_bundle_matches() -> None:
    check_verification_consistency(
        [{"id": "v1"}], [{"id": "v1"}], keep_local_verification=False
    )


def test_consistency_guard_bypassed_when_flag_on() -> None:
    # Canonical verification is authoritative (advances via weekly live verification),
    # so a lagging bundle snapshot must not raise when the flag is set.
    check_verification_consistency(
        [{"id": "v1"}], [{"id": "v2"}], keep_local_verification=True
    )
