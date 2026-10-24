---
name: new-endpoint
description: Create a new FastAPI REST endpoint following project conventions - router in app/api/v1, Pydantic schemas, registration in the v1 router, tests, and mirrored TS types in frontend/src/api. Use when asked to "add an endpoint", "new API resource", "CRUD for ...".
argument-hint: <resource> [description of methods]
---

# New endpoint: $ARGUMENTS

Before writing anything, read `backend/app/api/v1/health.py` and `backend/tests/test_health.py` as the style reference.

## Steps

1. **Schemas.** Create `backend/app/schemas/<resource>.py` (plus `__init__.py` if the folder is new) with Pydantic models:
   `<Resource>Create`, `<Resource>Read`, and `<Resource>Update` if needed. Typed fields; no `Optional` where a field is required.
2. **Router.** `backend/app/api/v1/<resource>.py`: `router = APIRouter(prefix="/<resources>", tags=["<resources>"])`.
   Handlers are `async def`, dependencies via `Annotated[..., Depends(...)]`, `response_model` on every route,
   explicit status codes (`status_code=201` for creation). Errors via `HTTPException` with a clear `detail`.
   Persistence: SQLAlchemy model in `app/models/<resource>.py` (import it in `app/models/__init__.py`), queries in
   `app/services/<resource>.py` taking an `AsyncSession`, handlers get the session via `db: DbSession`.
   Then create the migration with `/migration add_<resources>_table`.
3. **Registration.** Add `router.include_router(<resource>.router)` to `backend/app/api/v1/__init__.py`.
4. **Tests.** `backend/tests/api/v1/test_<resource>.py` (create folders and `__init__.py`). At minimum: a happy path per method
   and one negative case (422 on invalid data or 404 on a missing id). Use the `client` fixture, plus `db_required` for tests that hit the database.
5. **Frontend contract.** `frontend/src/api/<resource>.ts`: TS interfaces named after the Pydantic models,
   and request functions using `apiFetch` from `./client`. Do not create components unless asked.
6. **Verify.** From `backend/`: `uv run ruff format . && uv run ruff check . && uv run mypy app && uv run pytest -q`,
   and from `frontend/`: `npm run build`. Fix whatever fails.

## Report

List of created/changed files and the routes as `METHOD /api/v1/path → description`.
