.PHONY: env install lint format type test cov check up down logs seed migrate

env:
	python3 scripts/generate_env.py

install:
	uv sync --dev

lint:
	uv run ruff check apps packages tests
	uv run ruff format --check apps packages tests

format:
	uv run ruff format apps packages tests
	uv run ruff check --fix apps packages tests

type:
	uv run mypy apps packages

test:
	uv run pytest -q

cov:
	uv run pytest --cov --cov-report=term-missing -q

check: lint type test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f api worker

migrate:
	uv run alembic upgrade head

seed:
	uv run python -m scripts.seed
