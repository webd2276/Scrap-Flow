"""Authenticated encryption for transient automation secrets.

Secret values are sealed with AES-256-GCM and written to Redis under the job id.
They are never stored in PostgreSQL, job payloads, logs, or API responses.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from packages.core.settings import Settings

_NONCE_BYTES = 12
_HKDF_SALT = b"scrapeflow-automation-secrets"


class SecretBoxError(Exception):
    """Sealed secret material is unavailable, corrupt, or bound to another job."""


def encryption_key(settings: Settings) -> bytes:
    """Derive a 32-byte key from the dedicated setting or the JWT root secret."""
    if settings.automation_secret_key is not None:
        return hashlib.sha256(
            settings.automation_secret_key.get_secret_value().encode("utf-8")
        ).digest()
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=b"v1",
    ).derive(settings.jwt_secret.get_secret_value().encode("utf-8"))


def seal_secrets(
    values: dict[str, str],
    *,
    key: bytes,
    associated_data: bytes,
) -> str:
    """Encrypt a secret map into an opaque, URL-safe token."""
    nonce = os.urandom(_NONCE_BYTES)
    plaintext = json.dumps(values, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, associated_data)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def open_secrets(
    token: str,
    *,
    key: bytes,
    associated_data: bytes,
) -> dict[str, str]:
    """Decrypt a sealed map, rejecting tampered or cross-job tokens."""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise SecretBoxError("Secret material is not valid base64") from exc
    if len(raw) <= _NONCE_BYTES:
        raise SecretBoxError("Secret material is truncated")
    nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, associated_data)
    except InvalidTag as exc:
        raise SecretBoxError("Secret material failed authentication") from exc
    try:
        parsed = json.loads(plaintext)
    except json.JSONDecodeError as exc:
        raise SecretBoxError("Secret material is not valid JSON") from exc
    if not isinstance(parsed, dict) or not all(
        isinstance(name, str) and isinstance(value, str) for name, value in parsed.items()
    ):
        raise SecretBoxError("Secret material has an invalid shape")
    return parsed
