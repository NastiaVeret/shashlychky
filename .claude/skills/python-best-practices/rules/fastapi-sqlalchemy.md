# 6. FastAPI and SQLAlchemy idioms (High)

Project-specific rules live in `.claude/rules/backend.md` and `.claude/rules/database.md`; this file is the idiom layer on top.

## Layering

```
router  ->  service  ->  models / external clients
(HTTP)      (logic)      (I/O)
```

- Routers: parse input, call one service function, map domain errors to HTTP. No SQL, no business rules.
- Services: plain `async def` functions taking an `AsyncSession` and typed arguments, returning models or dataclasses. No `Request`, no `HTTPException`.
- Schemas (`app/schemas`) are the public contract; models (`app/models`) are storage. They are different classes even when the fields match today.

## Dependencies

`Annotated` aliases, defined once and reused: `DbSession`, `SettingsDep`, `CurrentUser`. A dependency that does I/O is `async def`. Use `yield` dependencies for setup/teardown.

## Responses

Always `response_model` and `status_code`. Return the schema instance, not a dict. For lists return `list[OrderRead]`, and paginate anything that can grow (`limit`/`offset` with maximums).

## Queries

```python
# Good: SQLAlchemy 2 style
stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(50)
orders = (await db.scalars(stmt)).all()
one = await db.get(Order, order_id)          # by primary key
```

- Load relationships explicitly (`selectinload`) when you will iterate them; lazy loading in async raises.
- Avoid N+1: one query with a join or `selectinload`, not a query per item in a loop.
- Bulk writes: `db.add_all(...)`, or `insert(Model).values([...])` for large batches.
- Let the `get_db` dependency commit. `await db.flush()` when you need generated ids mid-request.

## Transactions and errors

`IntegrityError` on a unique constraint is an expected race, not a crash: catch it in the service, roll back, raise `ConflictError`.

## Settings

Read `Settings` through the dependency, not `get_settings()` scattered in modules, so tests can override it with `app.dependency_overrides`.

## Startup/shutdown

Use the `lifespan` context manager in `create_app()` for engine disposal and shared clients. No `@app.on_event`.

## Logging

`logger = logging.getLogger(__name__)` at module top. Structured key=value messages. Never log passwords, tokens, or full request bodies.
