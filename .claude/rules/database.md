---
paths:
  - "backend/app/models/**"
  - "backend/app/db/**"
  - "backend/alembic/**"
  - "backend/alembic.ini"
---

# Database (PostgreSQL, SQLAlchemy 2, Alembic)

## Layout

```
app/db/base.py          Base (DeclarativeBase) with the naming convention for constraints
app/db/session.py       async engine, sessionmaker, get_db dependency, DbSession alias
app/models/<name>.py    one module per table/aggregate; every module imported in app/models/__init__.py
alembic/env.py          takes the URL from Settings; compare_type and compare_server_default are on
alembic/versions/       migrations, file name: YYYYMMDD_HHMM_<rev>_<slug>.py
```

Production: Cloud SQL Postgres, reached from Cloud Run via unix socket (`DB_HOST=/cloudsql/<connection name>`).
Password comes from Secret Manager (`db-password`) as the `DB_PASSWORD` env var. Local: `docker compose up -d db`.

## Models

- SQLAlchemy 2 style only: `Mapped[...]` + `mapped_column(...)`. No legacy `Column = Column(...)`.
- Table names: plural snake_case (`orders`, `order_items`). Primary key `id: Mapped[int]` identity, or `uuid.UUID` with `server_default=text("gen_random_uuid()")` when ids are exposed publicly.
- Timestamps: `created_at` / `updated_at` as `DateTime(timezone=True)` with `server_default=func.now()`. Never naive datetimes.
- Relationships: explicit `ForeignKey(..., ondelete=...)` and typed `relationship(back_populates=...)`.
- Never rely on constraint auto-names: the naming convention in `Base.metadata` makes them deterministic. Keep it.
- A new model is not done until it is imported in `app/models/__init__.py`, otherwise Alembic will not see it.

## Sessions

- Handlers get the session via `db: DbSession`. One session per request; `get_db` commits on success and rolls back on exception.
- Do not call `session.commit()` inside services unless you need an intermediate commit; let the dependency commit.
- Only async API: `await db.execute(...)`, `await db.get(...)`, `await db.flush()`. No sync `Session`.
- Queries with `select(Model).where(...)`; no `db.query(...)` legacy API.

## Migrations

- Every model change ships with a migration in the same PR. CI runs `alembic upgrade head` and `alembic check`; a drift between models and migrations fails CI.
- Create with autogenerate against a local database, then **read the generated file**: autogenerate misses renames, data moves, enum value changes, and some server defaults.
- One migration per PR unless there is a real reason. Slug describes the change: `add_orders_table`, `orders_add_status_index`.
- Migrations must be reversible: implement `downgrade()`; if genuinely impossible, raise `NotImplementedError` with a comment why.
- Deploy runs `alembic upgrade head` as a Cloud Run Job **before** the new backend revision starts, while the old revision is still serving. Therefore every migration must be backward compatible with the previous code version:
  - adding a column: nullable or with a server default;
  - removing or renaming a column: two PRs (first stop using it in code, then drop it);
  - large data backfills: separate migration or a script, not inside a schema migration that locks tables.
- Never edit a migration that is already merged into `main`. Add a new one.
- Raw SQL in migrations via `op.execute(text(...))` is fine when Alembic has no operation for it.

## Commands

```bash
uv run alembic upgrade head                      # apply
uv run alembic revision --autogenerate -m "slug" # generate from models (needs a running database)
uv run alembic check                             # models vs migrations drift
uv run alembic downgrade -1                      # revert the last one
uv run alembic history --verbose
```
