"""In-process job queue. Swap for Redis + RQ/Celery when you scale past one machine."""
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

import requests

from . import config
from .security import UnsafeURL, assert_safe_url


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=config.MAX_WORKERS)

    def submit(self, kind: str, fn: Callable[[], dict], webhook_url: str | None = None) -> str:
        self._cleanup()
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "kind": kind,
                "status": "queued",
                "created_at": time.time(),
                "finished_at": None,
                "result": None,
                "error": None,
            }
        self._pool.submit(self._run, job_id, fn, webhook_url)
        return job_id

    def _run(self, job_id: str, fn: Callable[[], dict], webhook_url: str | None) -> None:
        self._update(job_id, status="running")
        try:
            result = fn()
            self._update(job_id, status="done", result=result, finished_at=time.time())
        except Exception as exc:  # noqa: BLE001
            partial = getattr(exc, "partial", None)
            self._update(
                job_id,
                status="failed",
                error=f"{type(exc).__name__}: {str(exc)[:500]}",
                result=partial,
                finished_at=time.time(),
            )
        if webhook_url:
            self._notify(job_id, webhook_url)

    def _notify(self, job_id: str, webhook_url: str) -> None:
        try:
            assert_safe_url(webhook_url)
            job = self.get(job_id)
            requests.post(
                webhook_url,
                json={"id": job_id, "status": job["status"], "error": job["error"]},
                timeout=10,
            )
        except (UnsafeURL, requests.RequestException):
            pass  # webhook is best-effort; client can still poll

    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def _cleanup(self) -> None:
        cutoff = time.time() - config.JOB_TTL_SECONDS
        with self._lock:
            for jid in [j for j, v in self._jobs.items() if v["created_at"] < cutoff]:
                del self._jobs[jid]


store = JobStore()
