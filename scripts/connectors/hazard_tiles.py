from __future__ import annotations


def flood_tile_url(z: int = 10, x: int = 909, y: int = 403) -> str:
    return f"https://disaportaldata.gsi.go.jp/raster/01_flood_l2_shinsuishin/{z}/{x}/{y}.png"


def tile_response_is_valid(status_code: int, payload: bytes) -> bool:
    if status_code == 404:
        return True
    return 200 <= status_code < 300 and payload.startswith(b"\x89PNG\r\n\x1a\n")
