from __future__ import annotations

import json
from typing import Any


def administrative_area_page_url() -> str:
    return "https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03.html"


def is_geojson(payload: bytes) -> bool:
    try:
        data: Any = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return data.get("type") in {"FeatureCollection", "Feature"}
