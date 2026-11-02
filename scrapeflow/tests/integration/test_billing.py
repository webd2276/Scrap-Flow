from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest
from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.settings import Settings
from pydantic import SecretStr
from tests.integration.conftest import (
    OkProbe,
    RecordingDispatcher,
    auth_header,
    signup_payload,
)

WEBHOOK_SECRET = "whsec_test_scrapeflow"


class FakeStripe:
    class Customer:
        @staticmethod
        def create(**_kwargs: Any) -> dict[str, str]:
            return {"id": "cus_test_123"}

    class checkout:  # noqa: N801 - mirrors the Stripe SDK namespace
        class Session:
            @staticmethod
            def create(**_kwargs: Any) -> dict[str, str]:
                return {"url": "https://checkout.stripe.test/session"}

    class billing_portal:  # noqa: N801 - mirrors the Stripe SDK namespace
        class Session:
            @staticmethod
            def create(**_kwargs: Any) -> dict[str, str]:
                return {"url": "https://billing.stripe.test/session"}


@pytest.fixture
def billing_settings(integration_settings: Settings) -> Settings:
    return integration_settings.model_copy(
        update={
            "billing_enabled": True,
            "stripe_secret_key": SecretStr("sk_test_scrapeflow"),
            "stripe_webhook_secret": SecretStr(WEBHOOK_SECRET),
            "stripe_price_starter": "price_starter",
            "stripe_price_pro": "price_pro",
            "stripe_price_business": "price_business",
        }
    )


@pytest.fixture
def billing_client(
    billing_settings: Settings,
    dispatcher: RecordingDispatcher,
) -> Iterator[TestClient]:
    app = create_app(billing_settings, probes=[OkProbe()], dispatcher=dispatcher)
    with TestClient(app) as test_client:
        yield test_client


def _sign(payload: bytes, *, timestamp: int | None = None, secret: str = WEBHOOK_SECRET) -> str:
    moment = timestamp if timestamp is not None else int(time.time())
    signed = f"{moment}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={moment},v1={digest}"


def _event(event_id: str, event_type: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": event_id,
        "object": "event",
        "type": event_type,
        "data": {"object": obj},
    }


def _post_webhook(client: TestClient, event: dict[str, Any], signature: str | None = None) -> Any:
    payload = json.dumps(event).encode()
    return client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": signature or _sign(payload),
        },
    )


async def _fetchrow(settings: Settings, query: str, *args: object) -> asyncpg.Record | None:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        return await connection.fetchrow(query, *args)
    finally:
        await connection.close()


async def _org(settings: Settings, org_id: uuid.UUID) -> asyncpg.Record | None:
    return await _fetchrow(
        settings,
        "SELECT plan, billing_customer_id, billing_subscription_id "
        "FROM organizations WHERE id = $1",
        org_id,
    )


def test_billing_flag_gates_checkout(client: TestClient) -> None:
    token = client.post("/v1/auth/signup", json=signup_payload()).json()["access_token"]
    response = client.post(
        "/v1/billing/checkout",
        headers=auth_header(token),
        json={"plan": "starter"},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "BILLING_DISABLED"

    plans = client.get("/v1/billing/plans")
    assert plans.status_code == 200
    assert [plan["code"] for plan in plans.json()] == ["free", "starter", "pro", "business"]


def test_webhook_rejects_invalid_json(billing_client: TestClient) -> None:
    payload = b"not-json"
    response = billing_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign(payload),
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BILLING_ERROR"

    binary = b"\xff\xfe\x00"
    response = billing_client.post(
        "/v1/billing/webhook",
        content=binary,
        headers={
            "Content-Type": "application/json",
            "Stripe-Signature": _sign(binary),
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BILLING_ERROR"


def test_webhook_failed_event_can_be_reprocessed(
    billing_client: TestClient,
    billing_settings: Settings,
) -> None:
    broken = {
        "id": "evt_retry",
        "object": "event",
        "type": "checkout.session.completed",
        "data": {},
    }
    failed = _post_webhook(billing_client, broken)
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "BILLING_ERROR"

    row = asyncio.run(
        _fetchrow(
            billing_settings,
            "SELECT status, error FROM stripe_events WHERE event_id = $1",
            "evt_retry",
        )
    )
    assert row is not None
    assert row["status"] == "failed"
    assert row["error"]

    signup = billing_client.post("/v1/auth/signup", json=signup_payload())
    org_id = signup.json()["org_id"]
    fixed = _event(
        "evt_retry",
        "checkout.session.completed",
        {
            "id": "cs_retry",
            "object": "checkout.session",
            "client_reference_id": org_id,
            "customer": "cus_retry",
            "subscription": "sub_retry",
            "metadata": {"org_id": org_id, "plan": "starter"},
        },
    )
    retried = _post_webhook(billing_client, fixed)
    assert retried.status_code == 200, retried.text
    assert retried.json() == {"received": True, "duplicate": False}

    row = asyncio.run(
        _fetchrow(
            billing_settings,
            "SELECT status, error FROM stripe_events WHERE event_id = $1",
            "evt_retry",
        )
    )
    assert row is not None
    assert row["status"] == "processed"
    assert row["error"] is None


def test_subscription_event_matches_customer_and_price(
    billing_client: TestClient,
    billing_settings: Settings,
) -> None:
    signup = billing_client.post("/v1/auth/signup", json=signup_payload())
    org_id = uuid.UUID(signup.json()["org_id"])
    checkout = _event(
        "evt_customer_checkout",
        "checkout.session.completed",
        {
            "id": "cs_customer",
            "object": "checkout.session",
            "client_reference_id": str(org_id),
            "customer": "cus_customer",
            "subscription": "sub_customer",
            "metadata": {"org_id": str(org_id), "plan": "starter"},
        },
    )
    assert _post_webhook(billing_client, checkout).status_code == 200

    upgraded = _event(
        "evt_customer_upgrade",
        "customer.subscription.updated",
        {
            "id": "sub_customer",
            "object": "subscription",
            "customer": "cus_customer",
            "status": "active",
            "items": {"data": [{"price": {"id": "price_pro"}}]},
        },
    )
    assert _post_webhook(billing_client, upgraded).status_code == 200
    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["plan"] == "pro"

    cancelled = _event(
        "evt_customer_cancelled",
        "customer.subscription.updated",
        {
            "id": "sub_customer",
            "object": "subscription",
            "customer": "cus_customer",
            "status": "canceled",
        },
    )
    assert _post_webhook(billing_client, cancelled).status_code == 200
    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["plan"] == "free"

    ignored = _event(
        "evt_invoice_failed",
        "invoice.payment_failed",
        {"id": "in_1", "object": "invoice"},
    )
    ignored_response = _post_webhook(billing_client, ignored)
    assert ignored_response.status_code == 200
    assert ignored_response.json() == {"received": True, "duplicate": False}


def test_checkout_without_price_and_portal_without_customer(
    integration_settings: Settings,
    dispatcher: RecordingDispatcher,
) -> None:
    settings = integration_settings.model_copy(
        update={
            "billing_enabled": True,
            "stripe_secret_key": SecretStr("sk_test_scrapeflow"),
            "stripe_webhook_secret": SecretStr(WEBHOOK_SECRET),
            "stripe_price_starter": None,
        }
    )
    app = create_app(settings, probes=[OkProbe()], dispatcher=dispatcher)
    with TestClient(app) as client:
        signup = client.post("/v1/auth/signup", json=signup_payload())
        token = signup.json()["access_token"]
        checkout = client.post(
            "/v1/billing/checkout",
            headers=auth_header(token),
            json={"plan": "starter"},
        )
        assert checkout.status_code == 503
        assert checkout.json()["error"]["code"] == "BILLING_ERROR"

        portal = client.post("/v1/billing/portal", headers=auth_header(token), json={})
        assert portal.status_code == 409
        assert portal.json()["error"]["code"] == "CONFLICT"


def test_checkout_and_portal_without_network(
    billing_client: TestClient,
    billing_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("apps.api.services.billing._stripe_module", lambda: FakeStripe)
    signup = billing_client.post("/v1/auth/signup", json=signup_payload())
    assert signup.status_code == 201, signup.text
    token = signup.json()["access_token"]
    org_id = uuid.UUID(signup.json()["org_id"])

    checkout = billing_client.post(
        "/v1/billing/checkout",
        headers=auth_header(token),
        json={"plan": "starter"},
    )
    assert checkout.status_code == 200, checkout.text
    assert checkout.json()["url"] == "https://checkout.stripe.test/session"

    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["billing_customer_id"] == "cus_test_123"

    portal = billing_client.post("/v1/billing/portal", headers=auth_header(token), json={})
    assert portal.status_code == 200, portal.text
    assert portal.json()["url"] == "https://billing.stripe.test/session"


def test_webhook_rejects_bad_and_stale_signatures(billing_client: TestClient) -> None:
    event = _event("evt_bad", "checkout.session.completed", {"id": "cs_bad"})
    payload = json.dumps(event).encode()

    missing = billing_client.post(
        "/v1/billing/webhook",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert missing.status_code == 400
    assert missing.json()["error"]["code"] == "INVALID_SIGNATURE"

    invalid = _post_webhook(
        billing_client,
        event,
        signature=_sign(payload, secret="whsec_wrong"),
    )
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_SIGNATURE"

    stale = _post_webhook(
        billing_client,
        event,
        signature=_sign(payload, timestamp=int(time.time()) - 3600),
    )
    assert stale.status_code == 400
    assert stale.json()["error"]["code"] == "INVALID_SIGNATURE"


def test_webhook_applies_subscription_lifecycle_once(
    billing_client: TestClient,
    billing_settings: Settings,
) -> None:
    signup = billing_client.post("/v1/auth/signup", json=signup_payload())
    assert signup.status_code == 201, signup.text
    org_id = uuid.UUID(signup.json()["org_id"])

    checkout = _event(
        "evt_checkout",
        "checkout.session.completed",
        {
            "id": "cs_1",
            "object": "checkout.session",
            "client_reference_id": str(org_id),
            "customer": "cus_1",
            "subscription": "sub_1",
            "metadata": {"org_id": str(org_id), "plan": "starter"},
        },
    )
    first = _post_webhook(billing_client, checkout)
    assert first.status_code == 200, first.text
    assert first.json() == {"received": True, "duplicate": False}

    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["plan"] == "starter"
    assert org["billing_customer_id"] == "cus_1"
    assert org["billing_subscription_id"] == "sub_1"

    duplicate = _post_webhook(billing_client, checkout)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json() == {"received": True, "duplicate": True}

    upgraded = _event(
        "evt_upgrade",
        "customer.subscription.updated",
        {
            "id": "sub_1",
            "object": "subscription",
            "customer": "cus_1",
            "status": "active",
            "metadata": {"org_id": str(org_id)},
            "items": {"data": [{"price": {"id": "price_pro"}}]},
        },
    )
    assert _post_webhook(billing_client, upgraded).status_code == 200
    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["plan"] == "pro"

    deleted = _event(
        "evt_deleted",
        "customer.subscription.deleted",
        {
            "id": "sub_1",
            "object": "subscription",
            "customer": "cus_1",
            "status": "canceled",
            "metadata": {"org_id": str(org_id)},
        },
    )
    assert _post_webhook(billing_client, deleted).status_code == 200
    org = asyncio.run(_org(billing_settings, org_id))
    assert org is not None
    assert org["plan"] == "free"
    assert org["billing_subscription_id"] is None

    count = asyncio.run(_fetchrow(billing_settings, "SELECT count(*) AS count FROM stripe_events"))
    assert count is not None
    assert count["count"] == 3
