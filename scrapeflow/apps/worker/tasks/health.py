"""Worker liveness task used by compose/readiness smoke tests."""

from __future__ import annotations

from apps.worker.celery_app import celery_app


@celery_app.task(name="scrapeflow.ping")  # type: ignore[untyped-decorator]
def ping() -> str:
    return "pong"
