"""Stripe checkout, portal, and idempotent webhook processing."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from packages.core.errors import AppError, ErrorCode
from packages.core.models import Organization, OrgPlan, StripeEvent
from packages.core.plans import Plan, plan_for
from packages.core.settings import Settings
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.services.audit import add_audit

logger = structlog.get_logger(__name__)

_PRICE_FIELDS: dict[OrgPlan, str] = {
    OrgPlan.STARTER: "stripe_price_starter",
    OrgPlan.PRO: "stripe_price_pro",
    OrgPlan.BUSINESS: "stripe_price_business",
}


class BillingUnavailableError(RuntimeError):
    """Billing is disabled or misconfigured."""


def _stripe_module() -> Any:
    import stripe

    return stripe


def _price_map(settings: Settings) -> dict[str, OrgPlan]:
    mapping: dict[str, OrgPlan] = {}
    for plan, field in _PRICE_FIELDS.items():
        value = getattr(settings, field)
        if isinstance(value, str) and value:
            mapping[value] = plan
    return mapping


def _plan_value(raw: object) -> OrgPlan | None:
    if not isinstance(raw, str):
        return None
    try:
        return OrgPlan(raw)
    except ValueError:
        return None


def _org_id_from(raw: object) -> uuid.UUID | None:
    if not isinstance(raw, str):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


class BillingService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.billing_enabled

    def require_enabled(self) -> None:
        if not self.enabled:
            raise AppError(
                503,
                ErrorCode.BILLING_DISABLED,
                "Billing is not enabled on this deployment",
            )

    def plan_for_price(self, price_id: str) -> Plan | None:
        plan = _price_map(self._settings).get(price_id)
        return plan_for(plan) if plan is not None else None

    async def create_checkout(
        self,
        db: AsyncSession,
        *,
        org: Organization,
        plan: Plan,
        success_url: str,
        cancel_url: str,
    ) -> str:
        self.require_enabled()
        price_id = getattr(self._settings, _PRICE_FIELDS[plan.code])
        if not isinstance(price_id, str) or not price_id:
            raise AppError(
                503,
                ErrorCode.BILLING_ERROR,
                f"No Stripe price is configured for the {plan.name} plan",
            )

        def _create() -> tuple[str, str | None]:
            stripe = _stripe_module()
            stripe.api_key = self._settings.stripe_secret_key.get_secret_value()  # type: ignore[union-attr]
            customer_id = org.billing_customer_id
            created_customer: str | None = None
            if not customer_id:
                customer = stripe.Customer.create(
                    name=org.name,
                    metadata={"org_id": str(org.id), "slug": org.slug},
                )
                customer_id = str(customer["id"])
                created_customer = customer_id
            metadata = {"org_id": str(org.id), "plan": plan.code.value}
            session = stripe.checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                success_url=success_url,
                cancel_url=cancel_url,
                client_reference_id=str(org.id),
                metadata=metadata,
                subscription_data={"metadata": metadata},
                allow_promotion_codes=True,
            )
            return str(session["url"]), created_customer

        url, created_customer = await asyncio.to_thread(_create)
        if created_customer is not None:
            org.billing_customer_id = created_customer
        await db.flush()
        return url

    async def create_portal(
        self,
        *,
        org: Organization,
        return_url: str,
    ) -> str:
        self.require_enabled()
        if not org.billing_customer_id:
            raise AppError(
                409,
                ErrorCode.CONFLICT,
                "This organization has no Stripe customer yet",
            )

        def _create() -> str:
            stripe = _stripe_module()
            stripe.api_key = self._settings.stripe_secret_key.get_secret_value()  # type: ignore[union-attr]
            session = stripe.billing_portal.Session.create(
                customer=org.billing_customer_id,
                return_url=return_url,
            )
            return str(session["url"])

        return await asyncio.to_thread(_create)

    def verify_and_parse(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        self.require_enabled()
        if signature is None:
            raise AppError(
                400,
                ErrorCode.INVALID_SIGNATURE,
                "Missing Stripe-Signature header",
            )
        secret = self._settings.stripe_webhook_secret
        if secret is None:  # pragma: no cover - settings validator guarantees this
            raise AppError(503, ErrorCode.BILLING_ERROR, "Stripe webhook secret is not configured")
        try:
            payload_text = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise AppError(400, ErrorCode.BILLING_ERROR, "Invalid JSON payload") from exc
        try:
            stripe = _stripe_module()
            stripe.WebhookSignature.verify_header(
                payload_text,
                signature,
                secret.get_secret_value(),
                tolerance=self._settings.stripe_webhook_tolerance_seconds,
            )
        except Exception as exc:
            raise AppError(
                400,
                ErrorCode.INVALID_SIGNATURE,
                "Invalid Stripe signature",
            ) from exc
        try:
            parsed = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            raise AppError(400, ErrorCode.BILLING_ERROR, "Invalid JSON payload") from exc
        if not isinstance(parsed, dict):
            raise AppError(400, ErrorCode.BILLING_ERROR, "Invalid Stripe event")
        return parsed

    async def handle_event(
        self,
        db: AsyncSession,
        *,
        event: dict[str, Any],
    ) -> bool:
        """Process a verified event. Returns True when it was already handled."""
        event_id = event.get("id")
        event_type = event.get("type")
        if not isinstance(event_id, str) or not isinstance(event_type, str):
            raise AppError(400, ErrorCode.BILLING_ERROR, "Stripe event is missing id or type")

        inserted = (
            await db.execute(
                pg_insert(StripeEvent)
                .values(
                    event_id=event_id,
                    type=event_type,
                    status="processing",
                    payload=event,
                )
                .on_conflict_do_nothing(index_elements=["event_id"])
                .returning(StripeEvent.id)
            )
        ).scalar_one_or_none()

        record: StripeEvent | None = None
        if inserted is None:
            record = (
                await db.execute(
                    select(StripeEvent).where(StripeEvent.event_id == event_id).with_for_update()
                )
            ).scalar_one()
            if record.status == "processed":
                return True
            record.status = "processing"
            record.error = None
            await db.flush()
        else:
            record = await db.get(StripeEvent, inserted)
            if record is None:  # pragma: no cover - inserted id must exist
                raise AppError(500, ErrorCode.BILLING_ERROR, "Could not record Stripe event")

        try:
            await self._apply(db, event_id=event_id, event_type=event_type, event=event)
        except Exception as exc:
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"[:1000]
            await db.commit()
            logger.exception("billing.event_failed", event_id=event_id, event_type=event_type)
            raise AppError(
                500,
                ErrorCode.BILLING_ERROR,
                "Stripe event processing failed",
            ) from exc

        record.status = "processed"
        record.processed_at = datetime.now(UTC)
        record.error = None
        await db.commit()
        return False

    async def _apply(
        self,
        db: AsyncSession,
        *,
        event_id: str,
        event_type: str,
        event: dict[str, Any],
    ) -> None:
        data = event.get("data")
        if not isinstance(data, dict):
            raise ValueError("Stripe event has no data object")
        payload_object = data.get("object")
        if not isinstance(payload_object, dict):
            raise ValueError("Stripe event has no data.object")

        if event_type == "checkout.session.completed":
            await self._checkout_completed(db, payload_object)
        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            await self._subscription_event(db, event_type, payload_object)
        else:
            logger.info(
                "billing.event_ignored",
                event_id=event_id,
                event_type=event_type,
            )

    async def _checkout_completed(
        self,
        db: AsyncSession,
        session_object: dict[str, Any],
    ) -> None:
        metadata = session_object.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        org_id = _org_id_from(session_object.get("client_reference_id")) or _org_id_from(
            metadata.get("org_id")
        )
        if org_id is None:
            raise ValueError("Checkout session has no organization reference")
        org = await db.get(Organization, org_id)
        if org is None:
            raise ValueError(f"Organization {org_id} not found")

        customer = session_object.get("customer")
        subscription = session_object.get("subscription")
        if isinstance(customer, str):
            org.billing_customer_id = customer
        if isinstance(subscription, str):
            org.billing_subscription_id = subscription
        plan = _plan_value(metadata.get("plan"))
        if plan is not None:
            self._set_plan(db, org, plan, reason="checkout_completed")

    def _set_plan(
        self,
        db: AsyncSession,
        org: Organization,
        plan: OrgPlan,
        *,
        reason: str,
    ) -> None:
        if org.plan is plan:
            return
        previous = org.plan
        org.plan = plan
        add_audit(
            db,
            action="billing.plan_changed",
            resource_type="organization",
            org_id=org.id,
            resource_id=str(org.id),
            details={"previous": previous.value, "plan": plan.value, "reason": reason},
        )

    async def _subscription_event(
        self,
        db: AsyncSession,
        event_type: str,
        subscription: dict[str, Any],
    ) -> None:
        metadata = subscription.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        subscription_id = subscription.get("id")
        customer = subscription.get("customer")

        org: Organization | None = None
        org_id = _org_id_from(metadata.get("org_id"))
        if org_id is not None:
            org = await db.get(Organization, org_id)
        if org is None and isinstance(subscription_id, str):
            org = (
                await db.execute(
                    select(Organization).where(
                        Organization.billing_subscription_id == subscription_id
                    )
                )
            ).scalar_one_or_none()
        if org is None and isinstance(customer, str):
            org = (
                await db.execute(
                    select(Organization).where(Organization.billing_customer_id == customer)
                )
            ).scalar_one_or_none()
        if org is None:
            raise ValueError("Subscription has no matching organization")

        if isinstance(customer, str):
            org.billing_customer_id = customer

        if event_type == "customer.subscription.deleted":
            self._set_plan(db, org, OrgPlan.FREE, reason="subscription_deleted")
            org.billing_subscription_id = None
            return

        status = subscription.get("status")
        if isinstance(subscription_id, str):
            org.billing_subscription_id = subscription_id

        if status in {"active", "trialing"}:
            plan = _plan_value(metadata.get("plan")) or self._plan_from_items(subscription)
            if plan is not None:
                self._set_plan(db, org, plan, reason="subscription_active")
        elif status in {"canceled", "unpaid", "incomplete_expired"}:
            self._set_plan(db, org, OrgPlan.FREE, reason=f"subscription_{status}")
            org.billing_subscription_id = None

    def _plan_from_items(self, subscription: dict[str, Any]) -> OrgPlan | None:
        items = subscription.get("items")
        if not isinstance(items, dict):
            return None
        data = items.get("data")
        if not isinstance(data, list):
            return None
        price_map = _price_map(self._settings)
        for item in data:
            if not isinstance(item, dict):
                continue
            price = item.get("price")
            if isinstance(price, dict):
                price_id = price.get("id")
                if isinstance(price_id, str) and price_id in price_map:
                    return price_map[price_id]
        return None
