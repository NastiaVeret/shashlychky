from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import get_engine
from app.main import app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _database_reachable() -> bool:
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any connection failure means "no database here"
        return False


@pytest.fixture
async def db_required() -> None:
    """Skip when no database is reachable (local run without Postgres). CI always has one."""
    if not await _database_reachable():
        pytest.skip("database not reachable; start it with `docker compose up db` or set DB_* env")
