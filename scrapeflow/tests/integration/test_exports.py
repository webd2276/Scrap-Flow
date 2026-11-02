from __future__ import annotations

import asyncio
import csv
import io
import json
import uuid
from datetime import UTC, datetime

import asyncpg
from fastapi.testclient import TestClient
from packages.core.settings import Settings
from tests.integration.conftest import auth_header, signup_payload

PUBLIC_URL = "https://93.184.216.34/"


def _signup(client: TestClient, email: str = "owner@example.com", org: str = "Acme") -> str:
    response = client.post("/v1/auth/signup", json=signup_payload(email=email, org=org))
    assert response.status_code == 201, response.text
    return str(response.json()["access_token"])


async def _execute(settings: Settings, query: str, *args: object) -> None:
    connection = await asyncpg.connect(settings.asyncpg_dsn)
    try:
        await connection.execute(query, *args)
    finally:
        await connection.close()


def _csv_rows(body: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(body.decode("utf-8"))))


def _submit_job(client: TestClient, token: str) -> uuid.UUID:
    response = client.post("/v1/scrape", headers=auth_header(token), json={"url": PUBLIC_URL})
    assert response.status_code == 202, response.text
    return uuid.UUID(response.json()["job"]["id"])


def test_job_export_json_and_csv_escape_untrusted_values(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    job_id = _submit_job(client, token)
    result = {
        "title": '=HYPERLINK("http://evil")',
        "link": "@cmd",
        "nested": {"items": [1, {"label": "-danger"}]},
        "plain": "safe",
    }
    asyncio.run(
        _execute(
            integration_settings,
            "UPDATE jobs SET result = $2, status = 'succeeded', finished_at = $3 WHERE id = $1",
            job_id,
            json.dumps(result),
            datetime.now(UTC),
        )
    )

    exported_json = client.get(f"/v1/jobs/{job_id}/export?format=json", headers=auth_header(token))
    assert exported_json.status_code == 200, exported_json.text
    assert exported_json.headers["content-type"].startswith("application/json")
    assert (
        exported_json.headers["content-disposition"] == f'attachment; filename="job-{job_id}.json"'
    )
    assert exported_json.headers["x-content-type-options"] == "nosniff"
    payload = exported_json.json()
    assert payload["id"] == str(job_id)
    assert payload["status"] == "succeeded"
    assert payload["result"] == result

    exported_csv = client.get(f"/v1/jobs/{job_id}/export?format=csv", headers=auth_header(token))
    assert exported_csv.status_code == 200, exported_csv.text
    assert exported_csv.headers["content-type"].startswith("text/csv")
    assert exported_csv.headers["content-disposition"] == f'attachment; filename="job-{job_id}.csv"'
    rows = _csv_rows(exported_csv.content)
    assert len(rows) == 2
    header, row = rows
    values = dict(zip(header, row, strict=True))
    assert values["id"] == str(job_id)
    assert values["status"] == "succeeded"
    assert values["result.title"] == '\'=HYPERLINK("http://evil")'
    assert values["result.link"] == "'@cmd"
    assert values["result.nested.items[0]"] == "1"
    assert values["result.nested.items[1].label"] == "'-danger"
    assert values["result.plain"] == "safe"


def test_job_export_requires_ownership_and_a_valid_format(
    client: TestClient,
) -> None:
    token = _signup(client)
    job_id = _submit_job(client, token)
    other = _signup(client, email="other@example.com", org="Other")

    assert client.get(f"/v1/jobs/{job_id}/export", headers=auth_header(other)).status_code == 404
    assert (
        client.get(f"/v1/jobs/{job_id}/export?format=xml", headers=auth_header(token)).status_code
        == 422
    )


def test_schedule_export_streams_runs_as_json_and_csv(
    client: TestClient,
    integration_settings: Settings,
) -> None:
    token = _signup(client)
    created = client.post(
        "/v1/schedules",
        headers=auth_header(token),
        json={
            "name": "Export me",
            "kind": "scrape",
            "cron": "0 9 * * *",
            "timezone": "UTC",
            "template": {"url": PUBLIC_URL},
            "watched_fields": ["title"],
        },
    )
    assert created.status_code == 201, created.text
    schedule_id = uuid.UUID(created.json()["id"])

    run = client.post(f"/v1/schedules/{schedule_id}/run", headers=auth_header(token))
    assert run.status_code == 200, run.text
    run_id = uuid.UUID(run.json()["run"]["id"])
    asyncio.run(
        _execute(
            integration_settings,
            """
            UPDATE schedule_runs
            SET status = 'succeeded', values = $2, changes = $3, finished_at = $4,
                credits = 1
            WHERE id = $1
            """,
            run_id,
            json.dumps({"title": "=cmd", "count": 2}),
            json.dumps(
                [
                    {
                        "field": "title",
                        "type": "changed",
                        "previous": "old",
                        "current": "=cmd",
                    }
                ]
            ),
            datetime.now(UTC),
        )
    )

    exported_json = client.get(
        f"/v1/schedules/{schedule_id}/export?format=json",
        headers=auth_header(token),
    )
    assert exported_json.status_code == 200, exported_json.text
    assert exported_json.headers["content-type"].startswith("application/json")
    runs = exported_json.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == str(run_id)
    assert runs[0]["status"] == "succeeded"
    assert runs[0]["values"] == {"title": "=cmd", "count": 2}
    assert runs[0]["changes"][0]["field"] == "title"

    exported_csv = client.get(
        f"/v1/schedules/{schedule_id}/export?format=csv",
        headers=auth_header(token),
    )
    assert exported_csv.status_code == 200, exported_csv.text
    rows = _csv_rows(exported_csv.content)
    assert len(rows) == 2
    values = dict(zip(rows[0], rows[1], strict=True))
    assert values["run_id"] == str(run_id)
    assert values["status"] == "succeeded"
    assert values["values"] == json.dumps(
        {"count": 2, "title": "=cmd"}, separators=(",", ":"), sort_keys=True
    )
    assert json.loads(values["changes"])[0]["type"] == "changed"

    other = _signup(client, email="other@example.com", org="Other")
    assert (
        client.get(f"/v1/schedules/{schedule_id}/export", headers=auth_header(other)).status_code
        == 404
    )
    assert (
        client.get(
            f"/v1/schedules/{schedule_id}/export?format=xml", headers=auth_header(token)
        ).status_code
        == 422
    )
