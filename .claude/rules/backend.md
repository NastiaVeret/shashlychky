---
paths:
  - "backend/**"
---

# Backend (FastAPI)

## Layout

```
app/main.py             create_app() factory, middleware
app/core/config.py      Settings (pydantic-settings)
app/api/v1/             routers; one file = one resource (health.py, orders.py ...)
app/api/v1/__init__.py  wires routers into the v1 router
app/schemas/            Pydantic request/response models (create when needed)
app/services/           business logic with no FastAPI dependencies (create when needed)
tests/                  mirrors app/: tests/api/v1/test_orders.py
```

## Rules

- All handlers are `async def`. No blocking calls (files, sync drivers) inside handlers.
- Dependencies via `Annotated[..., Depends(...)]`, never as default argument values (ruff B008).
- Responses are always typed: `response_model=` plus a Pydantic return annotation. Never return bare `dict`.
- Errors: `HTTPException` with an explicit `status_code` and a clear `detail` message.
- Configuration only through `Settings`. No `os.environ` outside `config.py`.
- Full typing: `mypy --strict` must pass. `Any` only with a comment explaining why.
- Absolute imports: `from app.core.config import ...`.
- Line length 100, formatting by `ruff format`. Do not fight the formatter.

## Tests

- `pytest` + `httpx.AsyncClient` with `ASGITransport`; the `client` fixture lives in `tests/conftest.py`.
- Per endpoint, at minimum: one happy path + one negative case (validation error or 404).
- Test names describe behavior: `test_create_order_returns_201`, `test_get_missing_order_returns_404`.
- External services are mocked. Tests never touch the network.

## Pre-commit check

```bash
uv run ruff format . && uv run ruff check . && uv run mypy app && uv run pytest -q
```
