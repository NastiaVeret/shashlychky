from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import text

from app.core.errors import LLMUnavailableError
from app.db.session import get_engine
from app.main import app
from app.schemas.recipes import Ingredient, RecipeContent
from app.services.llm import LLMResult, get_llm

SAMPLE_RECIPE = RecipeContent(
    title="Омлет з помідорами",
    description="Швидкий сніданок з яєць і помідорів.",
    cooking_time_minutes=10,
    servings=2,
    ingredients=[
        Ingredient(name="Яйця", quantity=4, unit="шт", have_at_home=True),
        Ingredient(name="Помідор", quantity=1, unit="шт", have_at_home=True),
        Ingredient(name="Сіль", quantity=None, unit="за смаком", have_at_home=True),
    ],
    steps=["Збити яйця з сіллю.", "Нарізати помідор.", "Смажити 5 хвилин під кришкою."],
    tips=None,
    clarifying_question=None,
)


class FakeLLM:
    """Deterministic stand-in for Gemini. Records prompts so tests can assert on them."""

    def __init__(self, *, fail: Exception | None = None) -> None:
        self.fail = fail
        self.calls: list[dict[str, str]] = []

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        self.calls.append({"system": system, "user": user})
        if self.fail:
            raise self.fail
        data = schema.model_validate(SAMPLE_RECIPE.model_dump())
        return LLMResult(data=data, model="fake", prompt_tokens=10, output_tokens=20, latency_ms=5)


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    llm = FakeLLM()
    app.dependency_overrides[get_llm] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm, None)


@pytest.fixture
def failing_llm() -> Iterator[FakeLLM]:
    llm = FakeLLM(fail=LLMUnavailableError())
    app.dependency_overrides[get_llm] = lambda: llm
    yield llm
    app.dependency_overrides.pop(get_llm, None)


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
