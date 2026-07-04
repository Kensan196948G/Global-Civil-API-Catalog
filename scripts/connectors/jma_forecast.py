from __future__ import annotations

import json
from typing import Any


def forecast_url(area_code: str = "130000") -> str:
    return f"https://www.jma.go.jp/bosai/forecast/data/forecast/{area_code}.json"


def is_forecast_json(payload: bytes) -> bool:
    try:
        data: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(data, list) and all(
        "publishingOffice" in item for item in data if isinstance(item, dict)
    )
