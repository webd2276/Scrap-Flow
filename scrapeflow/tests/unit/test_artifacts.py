from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from packages.core.artifacts import ArtifactStore, ArtifactStoreError, safe_filename
from packages.core.settings import Settings


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        api_key_pepper="a" * 40,
        jwt_secret="b" * 40,
        webhook_secret_key="c" * 40,
        artifacts_local_dir=str(tmp_path / "artifacts"),
        **overrides,
    )


def test_local_round_trip_and_digest(tmp_path: Path) -> None:
    store = ArtifactStore(_settings(tmp_path))
    org_id, job_id = uuid.uuid4(), uuid.uuid4()
    stored = store.put(
        org_id=org_id,
        job_id=job_id,
        filename="result.json",
        content_type="application/json",
        data=b'{"ok":true}',
    )
    assert store.backend == "local"
    assert stored.size_bytes == 11
    assert len(stored.sha256) == 64
    assert store.get(stored.storage_key) == b'{"ok":true}'
    assert store.presigned_url(stored.storage_key) is None
    assert (store.local_root / stored.storage_key).is_file()


def test_filename_is_sanitised() -> None:
    assert safe_filename("../../etc/passwd") == "etc-passwd"
    assert safe_filename(" page.html ") == "page.html"
    assert safe_filename("") == "artifact.bin"
    assert "/" not in safe_filename("a/b")


def test_traversal_keys_are_rejected(tmp_path: Path) -> None:
    store = ArtifactStore(_settings(tmp_path))
    with pytest.raises(ArtifactStoreError):
        store.get("../outside")
    with pytest.raises(ArtifactStoreError):
        store.get("/etc/passwd")


def test_size_limit(tmp_path: Path) -> None:
    store = ArtifactStore(_settings(tmp_path, artifacts_max_bytes=1024))
    with pytest.raises(ArtifactStoreError):
        store.put(
            org_id=uuid.uuid4(),
            job_id=uuid.uuid4(),
            filename="large.bin",
            content_type="application/octet-stream",
            data=b"x" * 1025,
        )


def test_missing_artifact_is_typed(tmp_path: Path) -> None:
    store = ArtifactStore(_settings(tmp_path))
    with pytest.raises(ArtifactStoreError):
        store.get(f"{uuid.uuid4()}/{uuid.uuid4()}/missing.bin")
