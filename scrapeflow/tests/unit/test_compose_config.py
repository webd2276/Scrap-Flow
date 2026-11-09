"""Compose wiring guards for the settings only the workers need."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SHARED_KEYS = ("EGRESS_PROXY_URL", "ARTIFACTS_ENDPOINT", "SELENIUM_REMOTE_URL")


def _service_environment(compose_file: Path, service: str) -> dict[str, object]:
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    return document["services"][service]["environment"]


def test_dev_worker_keeps_shared_backend_environment() -> None:
    environment = _service_environment(ROOT / "docker-compose.yml", "worker")
    for key in SHARED_KEYS:
        assert key in environment, f"worker lost {key}; use the *backend-env merge"


def test_prod_worker_keeps_shared_backend_environment() -> None:
    environment = _service_environment(ROOT / "deploy" / "compose.prod.yml", "worker")
    for key in SHARED_KEYS:
        assert key in environment, f"worker lost {key}; use the *backend-env merge"
