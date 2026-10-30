from __future__ import annotations

from apps.api.main import create_app
from fastapi.testclient import TestClient
from packages.core.errors import AppError, ErrorCode
from packages.core.settings import Settings


def _app_with_failing_route(settings: Settings) -> object:
    app = create_app(settings)

    @app.get("/_test/boom")
    async def boom() -> None:
        raise AppError(
            409,
            ErrorCode.CONFLICT,
            "Already exists",
            details={"field": "name"},
            headers={"X-Test": "yes"},
        )

    @app.get("/_test/number")
    async def number(n: int) -> dict[str, int]:
        return {"n": n}

    return app


def test_app_error_uses_envelope_and_headers(settings: Settings) -> None:
    client = TestClient(_app_with_failing_route(settings))
    response = client.get("/_test/boom", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 409
    assert response.headers["X-Request-ID"] == "req-123"
    assert response.headers["X-Test"] == "yes"
    assert response.json() == {
        "error": {
            "code": "CONFLICT",
            "message": "Already exists",
            "details": {"field": "name"},
        },
        "request_id": "req-123",
    }


def test_validation_error_is_sanitised(settings: Settings) -> None:
    client = TestClient(_app_with_failing_route(settings))
    response = client.get("/_test/number?n=secret-value")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["loc"] == ["query", "n"]
    assert "secret-value" not in response.text


def test_unknown_route_uses_envelope(settings: Settings) -> None:
    client = TestClient(_app_with_failing_route(settings))
    response = client.get("/nope")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_request_id_is_generated_and_echoed(settings: Settings) -> None:
    client = TestClient(_app_with_failing_route(settings))
    generated = client.get("/health")
    request_id = generated.headers["X-Request-ID"]
    assert len(request_id) == 32

    echoed = client.get("/health", headers={"X-Request-ID": request_id})
    assert echoed.headers["X-Request-ID"] == request_id
