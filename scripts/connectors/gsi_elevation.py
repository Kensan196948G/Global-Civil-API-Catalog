from __future__ import annotations


def elevation_tile_url(z: int = 14, x: int = 14549, y: int = 6451) -> str:
    return f"https://cyberjapandata.gsi.go.jp/xyz/dem5a_png/{z}/{x}/{y}.png"


def looks_like_elevation_tile(payload: bytes) -> bool:
    return payload.startswith(b"\x89PNG\r\n\x1a\n") or bool(payload.strip())
