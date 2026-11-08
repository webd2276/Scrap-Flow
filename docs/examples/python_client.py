"""Minimal ScrapeFlow API client using only the Python standard library.

Set SCRAPEFLOW_BASE_URL and SCRAPEFLOW_API_KEY, then run:

    python examples/python_client.py https://example.com
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

BASE_URL = os.environ.get("SCRAPEFLOW_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.environ.get("SCRAPEFLOW_API_KEY", "")


class ApiError(RuntimeError):
    def __init__(self, status: int, body: dict[str, Any]) -> None:
        self.status = status
        self.code = body.get("error", {}).get("code", "UNKNOWN")
        self.request_id = body.get("request_id")
        super().__init__(f"{status} {self.code} (request_id={self.request_id})")


def request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    idempotency_key: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read() or b"{}")
        except json.JSONDecodeError:
            body = {"error": {"code": "HTTP_ERROR"}}
        raise ApiError(exc.code, body) from exc


def scrape_and_wait(url: str, *, timeout: float = 120.0) -> dict[str, Any]:
    job = request(
        "POST",
        "/v1/scrape",
        {
            "url": url,
            "render_js": False,
            "extract": {"text": True, "links": True},
        },
        idempotency_key=uuid.uuid4().hex,
    )
    job_id = job["job_id"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = request("GET", f"/v1/jobs/{job_id}")
        if current["status"] in {"succeeded", "failed", "cancelled", "timed_out"}:
            return current
        time.sleep(1.0)
    raise TimeoutError(f"job {job_id} did not finish in {timeout}s")


def main() -> int:
    if not API_KEY:
        print("Set SCRAPEFLOW_API_KEY to a key with the jobs:write scope.", file=sys.stderr)
        return 2
    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    job = scrape_and_wait(target)
    print(json.dumps(job, indent=2))
    return 0 if job["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
