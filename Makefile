# Shashlychky developer entry point. Run `make` or `make help` to list targets.
#
# Conventions: backend commands run through uv, frontend through npm, database through docker compose.
# DB_PORT controls the host port of the local Postgres (defaults to 5432; use 5434 if 5432 is taken).

SHELL := /bin/bash
.DEFAULT_GOAL := help

export DB_PORT ?= 5432
OPENAPI_TS := openapi-typescript@7.13.0   # pinned; not in package.json because it peers on TS 5.x
SCHEMA := frontend/src/api/schema.d.ts
OPENAPI_JSON := frontend/src/api/openapi.json

.PHONY: help install dev db db-stop backend frontend migrate migration seed types types-check \
        check check-backend check-frontend test test-backend format lint eval clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install backend + frontend dependencies, .env files and git pre-commit hooks
	cd backend && uv sync
	cd frontend && npm install
	@[ -f backend/.env ] || cp backend/.env.example backend/.env
	@[ -f frontend/.env ] || cp frontend/.env.example frontend/.env
	uvx pre-commit install
	@echo "✔ ready: put your Gemini key into backend/.env (GEMINI_API_KEY) and run 'make dev'"

db: ## Start local Postgres (docker compose) and wait until it accepts connections
	docker compose up -d db
	@until docker compose exec -T db pg_isready -U postgres -d shashlychky >/dev/null 2>&1; do sleep 1; done
	@echo "✔ postgres on localhost:$(DB_PORT)"

db-stop: ## Stop local Postgres
	docker compose stop db

migrate: db ## Apply Alembic migrations to the local database
	cd backend && uv run alembic upgrade head

migration: db ## Create a migration from model changes: make migration m="add_orders_table"
	@[ -n "$(m)" ] || { echo "usage: make migration m=\"slug\""; exit 1; }
	cd backend && uv run alembic upgrade head && uv run alembic revision --autogenerate -m "$(m)" \
		&& uv run ruff check --fix alembic/versions >/dev/null && uv run ruff format alembic/versions >/dev/null \
		&& uv run alembic upgrade head && uv run alembic check
	@echo "✔ review the new file in backend/alembic/versions/ before committing"

seed: migrate ## Insert sample data into the local database
	cd backend && uv run python -m scripts.seed

backend: ## Run the API with reload on http://localhost:8000 (docs at /docs)
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend: ## Run Vite dev server on http://localhost:5173 (proxies /api to :8000)
	cd frontend && npm run dev

dev: migrate ## Run database, backend and frontend together (Ctrl+C stops all)
	@trap 'kill 0' INT TERM; \
	( cd backend && uv run uvicorn app.main:app --reload --port 8000 ) & \
	( cd frontend && npm run dev ) & \
	wait

types: ## Regenerate frontend TypeScript types from the backend OpenAPI schema
	cd backend && uv run python -m scripts.export_openapi > ../$(OPENAPI_JSON)
	cd frontend && npx -y $(OPENAPI_TS) src/api/openapi.json -o src/api/schema.d.ts
	@echo "✔ $(SCHEMA) regenerated"

types-check: types ## Fail if committed types are stale (used in CI)
	@git diff --exit-code -- $(SCHEMA) $(OPENAPI_JSON) \
		|| { echo "✖ generated types are out of date: run 'make types' and commit"; exit 1; }

format: ## Format all code (ruff, prettier)
	cd backend && uv run ruff format . && uv run ruff check --fix .
	cd frontend && npm run format

lint: ## Lint + typecheck without tests
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts
	cd frontend && npm run lint && npm run format:check && npm run typecheck

test-backend: ## Backend tests (DB tests skip if Postgres is not running)
	cd backend && uv run pytest -q

test: test-backend ## All tests

check-backend: ## Everything CI runs for the backend
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app scripts && uv run pytest -q

check-frontend: ## Everything CI runs for the frontend
	cd frontend && npm run lint && npm run format:check && npm run build

check: check-backend check-frontend types-check ## Everything CI runs

clean: ## Remove build artifacts and caches
	rm -rf frontend/dist backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	find backend -name __pycache__ -type d -prune -exec rm -rf {} +
