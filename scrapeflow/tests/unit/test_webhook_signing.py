from __future__ import annotations

import json

import pytest
from packages.core.secretbox import SecretBoxError
from packages.core.settings import Settings
from packages.core.webhooks import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    SIGNATURE_PREFIX,
    TIMESTAMP_HEADER,
    build_headers,
    canonical_body,
    generate_secret,
    reveal_secret,
    seal_secret,
    sign,
    verify_signature,
)


def test_generated_secrets_are_strong_and_unique() -> None:
    secrets = {generate_secret() for _ in range(20)}
    assert len(secrets) == 20
    assert all(len(secret) >= 40 for secret in secrets)


def test_secret_sealing_roundtrip(settings: Settings) -> None:
    secret = generate_secret()
    sealed = seal_secret(secret, settings)
    assert secret not in sealed
    assert "secret" not in sealed
    assert reveal_secret(sealed, settings) == secret


def test_secret_sealing_rejects_wrong_key(settings: Settings) -> None:
    sealed = seal_secret(generate_secret(), settings)
    other = Settings.model_validate({**settings.model_dump(), "webhook_secret_key": "d" * 40})
    with pytest.raises(SecretBoxError):
        reveal_secret(sealed, other)


def test_secret_sealing_rejects_tampering(settings: Settings) -> None:
    sealed = seal_secret(generate_secret(), settings)
    tampered = sealed[:-2] + ("AA" if sealed[-2:] != "AA" else "BB")
    with pytest.raises(SecretBoxError):
        reveal_secret(tampered, settings)


def test_signature_covers_timestamp_and_body() -> None:
    secret = "whsec_test"
    body = b'{"a":1}'
    signature = sign(secret, 1_000, body)
    assert signature.startswith(SIGNATURE_PREFIX)
    assert verify_signature(secret, signature, 1_000, body, now=1_000)
    assert not verify_signature(secret, signature, 1_000, b'{"a":2}', now=1_000)
    assert not verify_signature(secret, signature, 1_001, body, now=1_000)
    assert not verify_signature("other", signature, 1_000, body, now=1_000)


def test_signature_rejects_expired_timestamps() -> None:
    secret = "whsec_test"
    body = b"{}"
    signature = sign(secret, 1_000, body)
    assert not verify_signature(secret, signature, 1_000, body, tolerance_seconds=300, now=1_301)
    assert verify_signature(secret, signature, 1_000, body, tolerance_seconds=300, now=1_300)


def test_canonical_body_is_deterministic() -> None:
    left = canonical_body({"b": [1, 2], "a": {"z": True, "y": None}})
    right = canonical_body({"a": {"y": None, "z": True}, "b": [1, 2]})
    assert left == right
    assert json.loads(left) == {"a": {"y": None, "z": True}, "b": [1, 2]}
    assert b" " not in left


def test_build_headers_signs_the_exact_body() -> None:
    secret = "whsec_test"
    body = canonical_body({"id": "evt_1"})
    headers = build_headers(
        secret=secret,
        event_type="job.completed",
        delivery_id="delivery-1",
        body=body,
        timestamp=1_700_000_000,
    )
    assert headers["Content-Type"] == "application/json"
    assert headers[EVENT_HEADER] == "job.completed"
    assert headers[DELIVERY_HEADER] == "delivery-1"
    assert headers[TIMESTAMP_HEADER] == "1700000000"
    assert verify_signature(
        secret,
        headers[SIGNATURE_HEADER],
        1_700_000_000,
        body,
        now=1_700_000_000,
    )
