"""Create the artifact bucket if it does not exist.

Run as a one-shot compose service (``minio-init``) before the API starts. Uses
the same environment variables as the application so credentials never appear
on the command line.
"""

from __future__ import annotations

import os
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def main() -> None:
    endpoint = _required("ARTIFACTS_ENDPOINT")
    bucket = os.getenv("ARTIFACTS_BUCKET", "scrapeflow")
    region = os.getenv("ARTIFACTS_REGION", "us-east-1")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=_required("ARTIFACTS_ACCESS_KEY"),
        aws_secret_access_key=_required("ARTIFACTS_SECRET_KEY"),
        use_ssl=os.getenv("ARTIFACTS_USE_SSL", "false").lower() == "true",
    )

    last_error: Exception | None = None
    for _attempt in range(30):
        try:
            client.head_bucket(Bucket=bucket)
            print(f"bucket {bucket!r} already exists")
            return
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                last_error = exc
        except BotoCoreError as exc:
            last_error = exc
        try:
            client.create_bucket(Bucket=bucket)
            print(f"created bucket {bucket!r}")
            return
        except (ClientError, BotoCoreError) as exc:
            last_error = exc
            time.sleep(1)

    raise SystemExit(f"could not create bucket {bucket!r}: {last_error}")


if __name__ == "__main__":
    main()
