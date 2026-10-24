---
name: migration
description: Create, review and apply an Alembic database migration following project rules - autogenerate from SQLAlchemy models, inspect the result, check backward compatibility with the running Cloud Run revision, run alembic check. Use when asked to "add a migration", "migrate the database", "add a column/table", "change the schema", or after editing a model in backend/app/models.
argument-hint: <short slug, e.g. add_orders_table> [what changed]
---

# Database migration: $ARGUMENTS

Read `.claude/rules/database.md` first. Work from `backend/`.

## 1. Make sure a database is reachable

```bash
cd backend && uv run python -c "from app.core.config import get_settings; print(get_settings().sqlalchemy_url)"
docker compose -f ../docker-compose.yml up -d db   # if nothing is listening on localhost:5432
uv run alembic upgrade head                        # bring the local database to the current head
```

If Docker is not available and no `DB_*` env points to a database, stop and tell the user; autogenerate cannot work without one.

## 2. Models

Confirm the model change is done and the module is imported in `backend/app/models/__init__.py`.
If the user described a change but did not write the model, write it now following the rules (Mapped/mapped_column, timezone-aware timestamps, explicit FKs).

## 3. Generate

```bash
uv run alembic revision --autogenerate -m "<slug>"
uv run ruff check --fix alembic/versions && uv run ruff format alembic/versions
```

## 4. Review the generated file (mandatory)

Open `backend/alembic/versions/<new file>` and check:

- It contains only the intended change. Remove unrelated noise (e.g. type churn autogenerate sometimes emits).
- Renames: autogenerate emits drop + add. Replace with `op.alter_column(..., new_column_name=...)` if a rename was intended.
- New NOT NULL column on an existing table: add `server_default` or make it nullable, then backfill in a later migration.
- `downgrade()` reverses `upgrade()` exactly.
- Backward compatibility with the currently deployed code: the migration runs before the new revision starts. Dropping or renaming something the old code still reads is a two-PR change; say so to the user.
- Indexes on big tables: consider `postgresql_concurrently=True` with `op.get_context().autocommit_block()`.

## 5. Verify

```bash
uv run alembic upgrade head
uv run alembic check                 # must print "No new upgrade operations detected."
uv run alembic downgrade -1 && uv run alembic upgrade head   # round trip
uv run ruff format . && uv run ruff check . && uv run mypy app && uv run pytest -q
```

## Report

Migration file name and revision id, a plain-language summary of the schema change, the downgrade path,
and any backward-compatibility caveat for the deploy. Remind that the migration runs automatically on merge to `main`.
