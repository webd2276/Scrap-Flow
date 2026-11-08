"""Webhook outbox enqueue and signed delivery with retry/DLQ."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from packages.core.errors import AppError, ErrorCode
from packages.core.models import (
    Job,
    JobStatus,
    Organization,
    Schedule,
    ScheduleRun,
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookEndpoint,
)
from packages.core.observability import record_webhook_delivery
from packages.core.settings import Settings
from packages.core.ssrf import SSRFPolicy, validate_url
from packages.core.webhooks import build_headers, canonical_body, reveal_secret
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from apps.worker import job_store

logger = structlog.get_logger(__name__)

DELIVERY_LOCK = "sf:webhooks:delivery:lock"
_STUCK_DELIVERY_SECONDS = 300


def _url_key(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _payload(
    delivery_id: uuid.UUID,
    event_type: str,
    data: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = now or datetime.now(UTC)
    return {
        "id": str(delivery_id),
        "type": event_type,
        "created_at": moment.isoformat().replace("+00:00", "Z"),
        "data": data,
    }


def _job_event_type(job: Job) -> str:
    if job.status is JobStatus.SUCCEEDED:
        return "job.completed"
    if job.status is JobStatus.CANCELLED:
        return "job.cancelled"
    return "job.failed"


def job_event_data(job: Job) -> dict[str, Any]:
    data: dict[str, Any] = {
        "job_id": str(job.id),
        "kind": job.kind.value,
        "status": job.status.value,
        "url": job.url,
        "credits": job.credits,
        "attempts": job.attempts,
        "created_at": job.created_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "duration_ms": job.duration_ms,
    }
    if job.error_code:
        data["error_code"] = job.error_code
    if job.error_message:
        data["error_message"] = job.error_message
    if job.schedule_id is not None:
        data["schedule_id"] = str(job.schedule_id)
    return data


async def _insert_delivery(
    session: AsyncSession,
    *,
    org_id: uuid.UUID,
    endpoint_id: uuid.UUID | None,
    url: str,
    event_type: str,
    dedupe_key: str,
    data: dict[str, Any],
    settings: Settings,
) -> bool:
    delivery_id = uuid.uuid4()
    payload = _payload(delivery_id, event_type, data)
    inserted = (
        await session.execute(
            pg_insert(WebhookDelivery)
            .values(
                id=delivery_id,
                org_id=org_id,
                endpoint_id=endpoint_id,
                url=url,
                event_type=event_type,
                payload=payload,
                dedupe_key=dedupe_key,
                status=WebhookDeliveryStatus.PENDING,
                attempts=0,
                max_attempts=settings.webhook_max_attempts,
                next_attempt_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(index_elements=["dedupe_key"])
            .returning(WebhookDelivery.id)
        )
    ).scalar_one_or_none()
    return inserted is not None


async def enqueue_job_webhooks(
    session: AsyncSession,
    *,
    job: Job,
    settings: Settings,
) -> int:
    org = await session.get(Organization, job.org_id)
    if org is None or org.webhook_secret_encrypted is None:
        logger.info("webhook.no_signing_secret", job_id=str(job.id))
        return 0
    event_type = _job_event_type(job)
    data = job_event_data(job)
    targets: dict[str, uuid.UUID | None] = {}
    explicit = job.payload.get("webhook_url") if isinstance(job.payload, dict) else None
    if isinstance(explicit, str) and explicit:
        targets[explicit] = None
    endpoints = (
        await session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.org_id == job.org_id,
                WebhookEndpoint.enabled.is_(True),
                WebhookEndpoint.events.contains([event_type]),
            )
        )
    ).scalars()
    for endpoint in endpoints:
        targets.setdefault(endpoint.url, endpoint.id)

    inserted = 0
    for url, endpoint_id in targets.items():
        dedupe_key = f"job:{job.id}:{event_type}:{_url_key(url)}"
        if await _insert_delivery(
            session,
            org_id=job.org_id,
            endpoint_id=endpoint_id,
            url=url,
            event_type=event_type,
            dedupe_key=dedupe_key,
            data=data,
            settings=settings,
        ):
            inserted += 1
    return inserted


async def enqueue_schedule_changed(
    session: AsyncSession,
    *,
    schedule: Schedule,
    run: ScheduleRun,
    changes: list[dict[str, Any]],
    settings: Settings,
) -> int:
    org = await session.get(Organization, schedule.org_id)
    if org is None or org.webhook_secret_encrypted is None:
        return 0
    endpoints = (
        await session.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.org_id == schedule.org_id,
                WebhookEndpoint.enabled.is_(True),
                WebhookEndpoint.events.contains(["schedule.changed"]),
            )
        )
    ).scalars()
    data = {
        "schedule_id": str(schedule.id),
        "schedule_name": schedule.name,
        "run_id": str(run.id),
        "job_id": str(run.job_id) if run.job_id else None,
        "changes": changes,
        "values": run.values or {},
    }
    inserted = 0
    for endpoint in endpoints:
        dedupe_key = f"schedule_run:{run.id}:changed:{_url_key(endpoint.url)}"
        if await _insert_delivery(
            session,
            org_id=schedule.org_id,
            endpoint_id=endpoint.id,
            url=endpoint.url,
            event_type="schedule.changed",
            dedupe_key=dedupe_key,
            data=data,
            settings=settings,
        ):
            inserted += 1
    return inserted


def _retry_delay(settings: Settings, attempts: int) -> float:
    base = settings.webhook_backoff_seconds * (2 ** max(0, attempts - 1))
    return min(float(base), 3600.0) + secrets.SystemRandom().uniform(
        0.0, settings.webhook_backoff_seconds / 2
    )


async def _record_result(
    *,
    settings: Settings,
    delivery_id: uuid.UUID,
    success: bool,
    retryable: bool,
    response_status: int | None,
    response_body: str | None,
    error: str | None,
) -> None:
    maker = job_store.sessionmaker(settings)
    async with maker() as session:
        delivery = await session.get(WebhookDelivery, delivery_id)
        if delivery is None:  # pragma: no cover - row is durable
            return
        now = datetime.now(UTC)
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.response_status = response_status
        delivery.response_body = response_body
        delivery.error = error[:2000] if error else None
        if success:
            delivery.status = WebhookDeliveryStatus.SUCCEEDED
            delivery.delivered_at = now
        elif retryable and delivery.attempts < delivery.max_attempts:
            delivery.status = WebhookDeliveryStatus.PENDING
            delivery.next_attempt_at = now + timedelta(
                seconds=_retry_delay(settings, delivery.attempts)
            )
        else:
            delivery.status = WebhookDeliveryStatus.DEAD
            delivery.next_attempt_at = now
        endpoint = (
            await session.get(WebhookEndpoint, delivery.endpoint_id)
            if delivery.endpoint_id is not None
            else None
        )
        if endpoint is not None:
            if success:
                endpoint.last_success_at = now
            else:
                endpoint.last_failure_at = now
        await session.commit()
        if success:
            outcome = "succeeded"
        elif delivery.status == WebhookDeliveryStatus.PENDING:
            outcome = "retrying"
        else:
            outcome = "dead"
        record_webhook_delivery(event=delivery.event_type, result=outcome)


async def _send(
    settings: Settings,
    delivery: WebhookDelivery,
    secret: str,
) -> tuple[bool, bool, int | None, str | None, str | None]:
    body = canonical_body(delivery.payload)
    headers = build_headers(
        secret=secret,
        event_type=delivery.event_type,
        delivery_id=str(delivery.id),
        body=body,
    )
    max_bytes = settings.webhook_max_response_bytes
    status: int | None = None
    body_bytes = bytearray()
    try:
        async with (
            httpx.AsyncClient(
                proxy=settings.egress_proxy_url,
                timeout=settings.webhook_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream("POST", delivery.url, content=body, headers=headers) as response,
        ):
            status = response.status_code
            async for chunk in response.aiter_bytes():
                if len(body_bytes) >= max_bytes:
                    break
                body_bytes.extend(chunk[: max_bytes - len(body_bytes)])
    except httpx.HTTPError as exc:
        return False, True, None, None, f"{type(exc).__name__}: {exc}"
    text = bytes(body_bytes).decode("utf-8", "replace")
    assert status is not None
    if 200 <= status < 300:
        return True, False, status, text, None
    if status in {408, 425, 429} or status >= 500:
        return False, True, status, text, f"HTTP {status}"
    return False, False, status, text, f"HTTP {status}"


async def deliver_pending(
    *,
    settings: Settings,
    limit: int | None = None,
) -> dict[str, int]:
    policy = SSRFPolicy(allowed_ports=settings.egress_port_set)
    batch = limit or settings.webhook_delivery_batch_size
    maker = job_store.sessionmaker(settings)
    now = datetime.now(UTC)
    async with maker() as session:
        await session.execute(
            update(WebhookDelivery)
            .where(
                WebhookDelivery.status == WebhookDeliveryStatus.DELIVERING,
                WebhookDelivery.last_attempt_at.is_not(None),
                WebhookDelivery.last_attempt_at < now - timedelta(seconds=_STUCK_DELIVERY_SECONDS),
            )
            .values(status=WebhookDeliveryStatus.PENDING, next_attempt_at=now)
        )
        await session.commit()
        due_ids = list(
            (
                await session.execute(
                    select(WebhookDelivery.id)
                    .where(
                        WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                        WebhookDelivery.next_attempt_at <= now,
                    )
                    .order_by(WebhookDelivery.next_attempt_at, WebhookDelivery.id)
                    .limit(batch)
                )
            ).scalars()
        )

    sent = failed = dead = 0
    for delivery_id in due_ids:
        async with maker() as session:
            delivery = (
                await session.execute(
                    select(WebhookDelivery)
                    .where(
                        WebhookDelivery.id == delivery_id,
                        WebhookDelivery.status == WebhookDeliveryStatus.PENDING,
                    )
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if delivery is None:
                continue
            delivery.status = WebhookDeliveryStatus.DELIVERING
            delivery.last_attempt_at = now
            await session.commit()
            delivery = await session.get(WebhookDelivery, delivery_id)
            if delivery is None:  # pragma: no cover
                continue
            org = await session.get(Organization, delivery.org_id)
            if org is None or org.webhook_secret_encrypted is None:
                await _record_result(
                    settings=settings,
                    delivery_id=delivery_id,
                    success=False,
                    retryable=False,
                    response_status=None,
                    response_body=None,
                    error="No webhook signing secret configured",
                )
                dead += 1
                continue
            endpoint = (
                await session.get(WebhookEndpoint, delivery.endpoint_id)
                if delivery.endpoint_id is not None
                else None
            )
            if endpoint is not None and not endpoint.enabled:
                await _record_result(
                    settings=settings,
                    delivery_id=delivery_id,
                    success=False,
                    retryable=False,
                    response_status=None,
                    response_body=None,
                    error="Endpoint disabled",
                )
                dead += 1
                continue
            try:
                target = await validate_url(delivery.url, policy)
                if target.scheme != "https":
                    raise AppError(
                        422,
                        ErrorCode.VALIDATION_ERROR,
                        "Webhook URLs must use HTTPS",
                    )
            except AppError as exc:
                await _record_result(
                    settings=settings,
                    delivery_id=delivery_id,
                    success=False,
                    retryable=False,
                    response_status=None,
                    response_body=None,
                    error=f"{exc.code.value}: {exc.message}",
                )
                dead += 1
                continue
            try:
                secret = reveal_secret(org.webhook_secret_encrypted, settings)
            except Exception as exc:
                await _record_result(
                    settings=settings,
                    delivery_id=delivery_id,
                    success=False,
                    retryable=False,
                    response_status=None,
                    response_body=None,
                    error=f"Secret unavailable: {type(exc).__name__}",
                )
                dead += 1
                continue

        try:
            success, retryable, status, body, error = await _send(settings, delivery, secret)
        except Exception as exc:  # defensive: never strand a delivery in DELIVERING
            success, retryable, status, body = False, True, None, None
            error = f"{type(exc).__name__}: {exc}"
        await _record_result(
            settings=settings,
            delivery_id=delivery.id,
            success=success,
            retryable=retryable,
            response_status=status,
            response_body=body,
            error=error,
        )
        if success:
            sent += 1
        elif retryable:
            failed += 1
        else:
            dead += 1

    logger.info("webhook.delivery_completed", sent=sent, retrying=failed, dead=dead)
    return {"sent": sent, "retrying": failed, "dead": dead}
