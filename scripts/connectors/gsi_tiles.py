from __future__ import annotations


def standard_tile_url(z: int = 10, x: int = 909, y: int = 403) -> str:
    return f"https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"


def is_png(payload: bytes) -> bool:
    return payload.startswith(b"\x89PNG\r\n\x1a\n")
