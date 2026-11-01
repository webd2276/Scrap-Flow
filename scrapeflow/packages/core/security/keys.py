"""API key generation, parsing, and peppered hashing.

Format: ``sf_live_<8-char prefix>_<43-char secret>``. Only the prefix and a
SHA-256(pepper || secret) digest are stored.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

KEY_PREFIX = "sf_live"
_PREFIX_BYTES = 6
_SECRET_BYTES = 32
_KEY_RE = re.compile(r"^sf_live_([A-Za-z0-9_-]{8})_([A-Za-z0-9_-]{20,64})$")


class InvalidApiKeyError(ValueError):
    """The supplied key is malformed."""


@dataclass(frozen=True, slots=True)
class GeneratedKey:
    plaintext: str
    prefix: str
    key_hash: str


@dataclass(frozen=True, slots=True)
class ParsedKey:
    prefix: str
    secret: str


def hash_secret(secret: str, pepper: str) -> str:
    return hashlib.sha256(f"{pepper}{secret}".encode()).hexdigest()


def generate_api_key(pepper: str) -> GeneratedKey:
    prefix = secrets.token_urlsafe(_PREFIX_BYTES)[:8]
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    plaintext = f"{KEY_PREFIX}_{prefix}_{secret}"
    return GeneratedKey(plaintext=plaintext, prefix=prefix, key_hash=hash_secret(secret, pepper))


def parse_api_key(raw: str) -> ParsedKey:
    match = _KEY_RE.fullmatch(raw.strip())
    if match is None:
        raise InvalidApiKeyError("Malformed API key")
    prefix, secret = match.groups()
    return ParsedKey(prefix=prefix, secret=secret)


def verify_secret(secret: str, expected_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_secret(secret, pepper), expected_hash)
