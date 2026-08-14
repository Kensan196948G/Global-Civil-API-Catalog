"""OpenAPI 3.x -> draft catalog entry candidates (issue #65, MVP).

Parses an OpenAPI 3.x document into one candidate per path (first method),
guesses category/security fields, and returns records compatible with
``web.api_v1.EntryCreate``.  Duplicate detection happens in the API against
existing records; this module stays pure (no DB, no network).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("気象", ("weather", "forecast", "気象", "予報")),
    ("地図", ("map", "tile", "geospatial", "地図")),
    ("河川", ("river", "water-level", "河川", "水位")),
    ("防災", ("disaster", "hazard", "flood", "防災", "災害")),
    ("環境", ("air", "environment", "大気", "環境")),
    ("行政", ("administrative", "行政")),
    ("交通", ("transport", "traffic", "交通")),
    ("地形", ("elevation", "terrain", "dem", "地形")),
    ("3D都市", ("3d", "citygml", "都市モデル")),
    ("国際水文", ("water", "hydrology", "水文")),
)

_METHODS = ("get", "post", "put", "patch", "delete")


def _guess_category(tags: list[str], summary: str, description: str) -> str:
    haystack = " ".join([*tags, summary, description]).lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword.lower() in haystack for keyword in keywords):
            return category
    return "周辺"


def _slug(value: str) -> str:
    ascii_value = re.sub(r"[^a-zA-Z0-9]+", "", value).lower()
    return (ascii_value or "api")[:12]


def build_candidates(
    spec: dict[str, Any], *, max_candidates: int = 10
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (candidates, errors). One candidate per path (first method)."""
    errors: list[str] = []
    info = spec.get("info") or {}
    servers = spec.get("servers") or []
    server_url = str(servers[0].get("url", "")) if servers else ""
    if not server_url.startswith(("http://", "https://")):
        errors.append("no usable server URL; using fictional placeholder")
        server_url = "https://example.test/openapi"
    components = spec.get("components") or {}
    schemes = components.get("securitySchemes") or {}
    has_security = bool(spec.get("security")) or bool(schemes)
    scheme_names = [str(key).lower() for key in schemes]
    api_key_required = "required" if has_security else "not_required"
    if any("oauth2" in name or "oidc" in name for name in scheme_names):
        auth_type = "oauth2"
    elif any("apikey" in name or "api_key" in name or "http" in name for name in scheme_names):
        auth_type = "api_key"
    else:
        auth_type = "other" if has_security else "none"

    title = str(info.get("title") or "OpenAPI API")
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:4].upper()
    slug = _slug(title)
    paths = spec.get("paths") or {}
    candidates: list[dict[str, Any]] = []

    for index, (path, item) in enumerate(sorted(paths.items()), start=1):
        if not isinstance(item, dict):
            continue
        method = next((m for m in _METHODS if m in item), None)
        if method is None:
            continue
        operation = item.get(method) or {}
        summary = str(
            operation.get("summary")
            or operation.get("operationId")
            or f"{method.upper()} {path}"
        )
        description = str(operation.get("description") or info.get("description") or "")
        tags = [str(tag) for tag in (operation.get("tags") or [])]
        endpoint = f"{server_url.rstrip('/')}{path}"
        has_braces = "{" in endpoint
        candidates.append(
            {
                "id": f"OPENAPI-{digest}-{index:03d}",
                "name": f"{title} - {summary}"[:200],
                "category": _guess_category(tags, summary, description),
                "sub_category": ", ".join(tags)[:100] or None,
                "provider": title[:200],
                "provider_type": "company",
                "region": "Global",
                "official_url": server_url,
                "document_url": server_url,
                "endpoint_template": endpoint,
                "sample_endpoint": None if has_braces else endpoint,
                "data_formats": ["JSON"],
                "api_key_required": api_key_required,
                "auth_type": auth_type,
                "license_note": str(
                    (info.get("license") or {}).get("name")
                    or "OpenAPI ドキュメントの利用条件を確認してください。"
                ),
                "commercial_use": "unknown",
                "update_frequency": "随時",
                "connection_status": "調査中",
                "trust_rank": "C",
                "connection_priority": 3,
                "business_fit_score": 50,
                "integration_score": 60,
                "tags": sorted(set([*tags, "openapi", slug]))[:20],
                "usage_summary": summary[:500],
                "usage_notes": "OpenAPI import により自動生成された候補です（レビュー必須）。",
                "risk_note": "自動生成のため、公式URL・利用条件・接続可否をレビューしてください。",
            }
        )
        if len(candidates) >= max_candidates:
            break
    return candidates, errors
