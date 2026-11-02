"""Artifact storage.

S3/MinIO is used when ``ARTIFACTS_ENDPOINT`` is set; otherwise files land in
``ARTIFACTS_LOCAL_DIR`` for development and tests. Storage keys are generated
server-side, never taken from user input, and are checked for traversal before
any local filesystem operation.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packages.core.settings import Settings

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactStoreError(RuntimeError):
    """Storage is unavailable or the object could not be read."""


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    storage_key: str
    size_bytes: int
    sha256: str
    etag: str | None = None


def safe_filename(value: str, *, fallback: str = "artifact.bin") -> str:
    name = _SAFE_NAME.sub("-", value.strip()).strip(".-")
    return (name or fallback)[:120]


class ArtifactStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._local_root = Path(settings.artifacts_local_dir).resolve()
        self._client: Any | None = None

    @property
    def backend(self) -> str:
        return "s3" if self._settings.artifacts_endpoint else "local"

    @property
    def local_root(self) -> Path:
        return self._local_root

    def storage_key(self, org_id: uuid.UUID, job_id: uuid.UUID, filename: str) -> str:
        return f"{org_id}/{job_id}/{uuid.uuid4().hex}-{safe_filename(filename)}"

    def put(
        self,
        *,
        org_id: uuid.UUID,
        job_id: uuid.UUID,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> StoredArtifact:
        limit = self._settings.artifacts_max_bytes
        if len(data) > limit:
            raise ArtifactStoreError(f"Artifact exceeds the {limit} byte limit")
        key = self.storage_key(org_id, job_id, filename)
        digest = hashlib.sha256(data).hexdigest()
        if self._settings.artifacts_endpoint:
            etag = self._put_s3(key, content_type, data)
        else:
            self._put_local(key, data)
            etag = None
        return StoredArtifact(storage_key=key, size_bytes=len(data), sha256=digest, etag=etag)

    def get(self, storage_key: str) -> bytes:
        if self._settings.artifacts_endpoint:
            return self._get_s3(storage_key)
        path = self._local_path(storage_key)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise ArtifactStoreError("Artifact is missing from storage") from exc

    def presigned_url(self, storage_key: str) -> str | None:
        if not self._settings.artifacts_endpoint:
            return None
        try:
            return str(
                self._s3().generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self._settings.artifacts_bucket,
                        "Key": storage_key,
                    },
                    ExpiresIn=self._settings.artifact_presign_seconds,
                )
            )
        except Exception as exc:  # pragma: no cover - provider specific
            raise ArtifactStoreError("Could not sign an artifact URL") from exc

    def _local_path(self, storage_key: str) -> Path:
        if storage_key.startswith("/") or ".." in Path(storage_key).parts:
            raise ArtifactStoreError("Invalid artifact key")
        resolved = (self._local_root / storage_key).resolve()
        if self._local_root not in resolved.parents:
            raise ArtifactStoreError("Invalid artifact key")
        return resolved

    def _put_local(self, storage_key: str, data: bytes) -> None:
        path = self._local_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            raise ArtifactStoreError("Could not store artifact") from exc
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _s3(self) -> Any:
        if self._client is None:
            import boto3

            access_key = (
                self._settings.artifacts_access_key.get_secret_value()
                if self._settings.artifacts_access_key
                else None
            )
            secret_key = (
                self._settings.artifacts_secret_key.get_secret_value()
                if self._settings.artifacts_secret_key
                else None
            )
            self._client = boto3.client(
                "s3",
                endpoint_url=self._settings.artifacts_endpoint,
                region_name=self._settings.artifacts_region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                use_ssl=self._settings.artifacts_use_ssl,
            )
        return self._client

    def _put_s3(self, storage_key: str, content_type: str, data: bytes) -> str | None:
        try:
            response = self._s3().put_object(
                Bucket=self._settings.artifacts_bucket,
                Key=storage_key,
                Body=data,
                ContentType=content_type,
            )
            return str(response.get("ETag") or "") or None
        except Exception as exc:
            raise ArtifactStoreError("Artifact upload failed") from exc

    def _get_s3(self, storage_key: str) -> bytes:
        try:
            response = self._s3().get_object(
                Bucket=self._settings.artifacts_bucket, Key=storage_key
            )
            return bytes(response["Body"].read())
        except Exception as exc:
            raise ArtifactStoreError("Artifact download failed") from exc
