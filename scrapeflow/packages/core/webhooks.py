"""Webhook signing secrets and HMAC request signing.

The signing secret must remain recoverable so the worker can HMAC outgoing
requests, therefore it is sealed with AES-256-GCM under ``WEBHOOK_SECRET_KEY``
instead of being hashed. Nothing ever logs or returns a stored secret; the
plaintext is returned exactly once when it is created or rotated.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from packages.core.secretbox import open_secrets, seal_secrets
from packages.core.settings import Settings

SECRET_BYTES = 32
SIGNATURE_HEADER = "X-ScrapeFlow-Signature"
TIMESTAMP_HEADER = "X-ScrapeFlow-Timestamp"
EVENT_HEADER = "X-ScrapeFlow-Event"
DELIVERY_HEADER = "X-ScrapeFlow-Delivery"
SIGNATURE_PREFIX = "sha256="
_ASSOCIATED_DATA = b"scrapeflow-webhook-secret:v1"


def _key(settings: Settings) -> bytes:
    return hashlib.sha256(settings.webhook_secret_key.get_secret_value().encode("utf-8")).digest()


def generate_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def seal_secret(secret: str, settings: Settings) -> str:
    return seal_secrets({"secret": secret}, key=_key(settings), associated_data=_ASSOCIATED_DATA)


def reveal_secret(sealed: str, settings: Settings) -> str:
    values = open_secrets(sealed, key=_key(settings), associated_data=_ASSOCIATED_DATA)
    secret = values.get("secret")
    if not secret:
        raise ValueError("Webhook secret material is empty")
    return secret


def sign(secret: str, timestamp: int, body: bytes) -> str:
    signed = f"{timestamp}.".encode() + body
    return SIGNATURE_PREFIX + hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()


def verify_signature(
    secret: str,
    signature: str,
    timestamp: int,
    body: bytes,
    *,
    tolerance_seconds: int = 300,
    now: int | None = None,
) -> bool:
    moment = int(time.time()) if now is None else now
    if abs(moment - timestamp) > tolerance_seconds:
        return False
    return hmac.compare_digest(sign(secret, timestamp, body), signature)


def canonical_body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def build_headers(
    *,
    secret: str,
    event_type: str,
    delivery_id: str,
    body: bytes,
    timestamp: int | None = None,
) -> dict[str, str]:
    moment = int(time.time()) if timestamp is None else timestamp
    return {
        "Content-Type": "application/json",
        "User-Agent": "ScrapeFlow-Webhook/0.1",
        EVENT_HEADER: event_type,
        DELIVERY_HEADER: delivery_id,
        TIMESTAMP_HEADER: str(moment),
        SIGNATURE_HEADER: sign(secret, moment, body),
    }
