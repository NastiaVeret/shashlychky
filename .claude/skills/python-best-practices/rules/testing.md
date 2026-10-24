# 8. Tests (Medium)

## Shape

- Arrange / Act / Assert, visibly separated. One behaviour per test.
- Name states the behaviour: `test_create_order_without_items_returns_422`.
- Test through the public surface (HTTP via `client`, or a service function), not private helpers.
- Assert on content, not just status: `assert body["status"] == "paid"`.

## Fixtures

- `conftest.py` holds shared fixtures (`client`, `db_required`); test files hold local ones.
- Prefer small factory functions (`make_order(**overrides)`) over giant fixtures that build the world.
- Database tests create their own rows with unique values and clean up (or run in a transaction that is rolled back).

## Parametrize instead of copy-paste

```python
@pytest.mark.parametrize(("quantity", "status"), [(0, 422), (-1, 422), (1, 201)])
async def test_create_order_validates_quantity(client, quantity, status): ...
```

## Isolation

- No network, no real clock, no real external services: `monkeypatch`, `respx` for httpx, `freezegun`-style fixed times.
- Override FastAPI dependencies with `app.dependency_overrides[get_settings] = lambda: Settings(...)` and clear them after.
- Tests do not depend on each other or on execution order.

## What to test

- Every endpoint: happy path, validation failure, not-found/conflict where applicable.
- Every branch in a service that encodes a business rule.
- Migrations: CI runs `alembic upgrade head` and `alembic check`; no unit tests for migrations needed.

## What not to test

- Framework behaviour (Pydantic validating an `int`), third-party libraries, trivial getters.
- Implementation details that a refactor would legitimately change.

## Speed

Unit tests run in milliseconds. If a test needs sleep, it is testing the wrong thing; make time injectable.
