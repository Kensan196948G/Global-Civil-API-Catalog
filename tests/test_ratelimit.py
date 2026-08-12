"""Unit tests for the in-memory fixed-window rate limiter."""

from web.ratelimit import RateLimiter


def test_allow_until_limit_then_deny() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)

    assert limiter.allow("ip", now=100.0)
    assert limiter.allow("ip", now=100.5)
    assert limiter.allow("ip", now=101.0)
    assert not limiter.allow("ip", now=101.5)


def test_window_resets_counter() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("ip", now=100.0)
    assert not limiter.allow("ip", now=159.9)
    assert limiter.allow("ip", now=160.0)


def test_keys_are_independent() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)

    assert limiter.allow("a", now=100.0)
    assert not limiter.allow("a", now=100.1)
    assert limiter.allow("b", now=100.2)


def test_reset_clears_key() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow("ip", now=100.0)
    assert not limiter.allow("ip", now=100.1)

    limiter.reset("ip")
    assert limiter.allow("ip", now=100.2)


def test_invalid_parameters_rejected() -> None:
    try:
        RateLimiter(0, 60)
    except ValueError:
        pass
    else:
        raise AssertionError("limit=0 must be rejected")
