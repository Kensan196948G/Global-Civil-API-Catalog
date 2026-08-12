"""Small in-memory fixed-window rate limiter.

The deployment runs a single uvicorn worker behind the static reverse proxy
(web/server.py), so an in-memory counter is sufficient. Login attempts are
keyed by the proxied client IP (X-Forwarded-For); write operations are keyed
by the session id / client IP as a fallback.
"""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        if limit < 1 or window_seconds < 1:
            raise ValueError("limit and window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Consume one token; True when the request is within the window."""
        now = time.monotonic() if now is None else now
        with self._lock:
            window_start, count = self._buckets.get(key, (0.0, 0))
            if now - window_start >= self.window_seconds:
                window_start, count = now, 0
            if count >= self.limit:
                return False
            self._buckets[key] = (window_start, count + 1)
            if len(self._buckets) > 4096:
                cutoff = now - self.window_seconds
                self._buckets = {
                    k: v for k, v in self._buckets.items() if v[0] > cutoff
                }
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)
