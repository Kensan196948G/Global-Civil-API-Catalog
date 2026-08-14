"""Outbound webhook delivery (MVP notifications, epic #49 step 2).

Events are dispatched synchronously with a short per-subscription timeout
so the catalog UI stays simple; a failed delivery never fails the caller --
the subscription row records ``last_delivery_status`` / ``failure_count``
for monitoring.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import WEBHOOK_EVENTS, WebhookSubscription

DELIVERY_TIMEOUT_SECONDS = 5.0
USER_AGENT = "Global-Civil-API-Catalog/1.3.0 webhook"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def deliver(
    subscription: WebhookSubscription,
    event: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    """Deliver one event; returns (delivery_id, status text)."""
    delivery_id = uuid.uuid4().hex
    body = json.dumps(
        {
            "id": delivery_id,
            "event": event,
            "at": _now().isoformat(),
            "data": payload,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "X-Catalog-Webhook-Event": event,
        "X-Catalog-Delivery": delivery_id,
    }
    if subscription.secret:
        headers["X-Catalog-Signature"] = (
            f"sha256={sign_payload(body, subscription.secret)}"
        )
    try:
        response = httpx.post(
            subscription.url,
            content=body,
            headers=headers,
            timeout=DELIVERY_TIMEOUT_SECONDS,
        )
        status = f"HTTP {response.status_code}"
        ok = 200 <= response.status_code < 300
    except Exception as exc:  # noqa: BLE001 - stable status text for the UI.
        status = f"error: {type(exc).__name__}"
        ok = False
    subscription.last_delivery_at = _now()
    subscription.last_delivery_status = status
    subscription.failure_count += 0 if ok else 1
    return delivery_id, status


def dispatch_webhooks(
    session: Session,
    event: str,
    payload: dict[str, Any],
) -> list[dict[str, str]]:
    """Deliver ``event`` to every active subscription that wants it."""
    if event not in WEBHOOK_EVENTS:
        return []
    subscriptions = session.scalars(
        select(WebhookSubscription).where(WebhookSubscription.is_active.is_(True))
    ).all()
    results: list[dict[str, str]] = []
    for subscription in subscriptions:
        if event not in subscription.events:
            continue
        delivery_id, status = deliver(subscription, event, payload)
        results.append(
            {
                "id": subscription.id,
                "delivery_id": delivery_id,
                "status": status,
            }
        )
    if results:
        session.commit()
    return results
