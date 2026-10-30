"""Importable ASGI application for uvicorn/gunicorn."""

from __future__ import annotations

from apps.api.main import create_app

app = create_app()
