# Backend (FastAPI)

```bash
uv sync                                # install dependencies (including dev)
uv run uvicorn app.main:app --reload   # http://localhost:8000/docs
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy app
```
