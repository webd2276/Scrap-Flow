import logging
import secrets
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, HttpUrl

from . import config
from .automation import run_steps
from .jobs import store
from .scraper import scrape
from .security import UnsafeURL, assert_safe_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="ScrapeFlow", version="1.0.0")


def require_key(x_api_key: str = Header(default="")) -> str:
    if not config.API_KEYS:
        raise HTTPException(503, "Server has no API_KEYS configured")
    if not any(secrets.compare_digest(x_api_key, k) for k in config.API_KEYS):
        raise HTTPException(401, "Invalid or missing X-API-Key")
    return x_api_key


class ScrapeRequest(BaseModel):
    url: HttpUrl
    selectors: dict[str, Any] | None = Field(
        default=None, description='{"title": "h1", "links": {"css": "a", "attr": "href"}}'
    )
    wait_for: str | None = Field(default=None, description="CSS selector to wait for (JS-heavy pages)")
    screenshot: bool = False
    include_html: bool = False
    find_contacts: bool = Field(default=False, description="Extract emails/phones found on the page")
    webhook_url: HttpUrl | None = None


class AutomateRequest(BaseModel):
    steps: list[dict[str, Any]]
    webhook_url: HttpUrl | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/scrape", status_code=202, dependencies=[Depends(require_key)])
def create_scrape(req: ScrapeRequest) -> dict[str, str]:
    try:
        assert_safe_url(str(req.url))
    except UnsafeURL as exc:
        raise HTTPException(400, str(exc)) from exc
    job_id = store.submit(
        "scrape",
        lambda: scrape(
            str(req.url),
            selectors=req.selectors,
            wait_for=req.wait_for,
            screenshot=req.screenshot,
            include_html=req.include_html,
            find_contacts=req.find_contacts,
        ),
        webhook_url=str(req.webhook_url) if req.webhook_url else None,
    )
    return {"job_id": job_id, "status_url": f"/v1/jobs/{job_id}"}


@app.post("/v1/automate", status_code=202, dependencies=[Depends(require_key)])
def create_automation(req: AutomateRequest) -> dict[str, str]:
    if len(req.steps) > config.MAX_STEPS:
        raise HTTPException(400, f"Too many steps (max {config.MAX_STEPS})")
    job_id = store.submit(
        "automate",
        lambda: run_steps(req.steps),
        webhook_url=str(req.webhook_url) if req.webhook_url else None,
    )
    return {"job_id": job_id, "status_url": f"/v1/jobs/{job_id}"}


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(require_key)])
def get_job(job_id: str) -> dict[str, Any]:
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found (or expired)")
    return job
