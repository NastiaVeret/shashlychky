# Backend (FastAPI)

```bash
uv sync                                # install dependencies (including dev)
docker compose up -d db                # local Postgres (from the repo root)
uv run alembic upgrade head            # apply migrations
uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```

Migrations: see `.claude/rules/database.md` or run `/migration` in Claude Code.
