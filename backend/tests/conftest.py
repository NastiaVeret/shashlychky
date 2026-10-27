from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import text

from app.core.errors import LLMUnavailableError
from app.db.session import get_engine
from app.main import app
from app.schemas.nutrition import NutritionFacts
from app.schemas.recipes import Ingredient, RecipeContent, Unit
from app.services.llm import LLMResult, get_llm
from app.services.nutrition import ProductNutrition, get_nutrition_provider

SAMPLE_RECIPE = RecipeContent(
    title="Омлет з помідорами",
    description="Швидкий сніданок з яєць і помідорів.",
    cooking_time_minutes=10,
    servings=2,
    ingredients=[
        Ingredient(name="Яйця", quantity=4, unit=Unit.PIECE, have_at_home=True),
        Ingredient(name="Помідор", quantity=1, unit=Unit.PIECE, have_at_home=True),
        Ingredient(name="Сіль", quantity=None, unit=Unit.TO_TASTE, have_at_home=True),
    ],
    steps=["Збити яйця з сіллю.", "Нарізати помідор.", "Смажити 5 хвилин під кришкою."],
    tips=None,
    clarifying_question=None,
)


class FakeLLM:
    """Deterministic stand-in for Gemini. Records prompts so tests can assert on them."""

    def __init__(
        self, *, fail: Exception | None = None, responses: list[RecipeContent] | None = None
    ) -> None:
        self.fail = fail
        # Returned in order, one per call; SAMPLE_RECIPE once the queue is empty.
        self.responses = list(responses or [])
        self.calls: list[dict[str, str]] = []

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        self.calls.append({"system": system, "user": user})
        if self.fail:
            raise self.fail
        recipe = self.responses.pop(0) if self.responses else SAMPLE_RECIPE
        data = schema.model_validate(recipe.model_dump())
        return LLMResult(data=data, model="fake", prompt_tokens=10, output_tokens=20, latency_ms=5)


class FakeNutrition:
    """Stand-in for the Silpo nutrition lookup: answers from a fixed name -> product map."""

    def __init__(self, products: dict[str, ProductNutrition | None]) -> None:
        self.products = products
        self.calls: list[list[str]] = []

    async def lookup(self, names: list[str]) -> dict[str, ProductNutrition | None]:
        self.calls.append(names)
        return {n: self.products.get(n) for n in names}


# 1 piece of tomato sold as "150г"; eggs not found in the catalogue
SAMPLE_NUTRITION = {
    "Помідор": ProductNutrition(
        product_name="Помідор рожевий",
        per_100g=NutritionFacts(kcal=20, protein_g=1, fat_g=0.2, carbs_g=4),
        package_grams=150,
    ),
}


@pytest.fixture
def fake_nutrition() -> Iterator[FakeNutrition]:
    provider = FakeNutrition(SAMPLE_NUTRITION)
    app.dependency_overrides[get_nutrition_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_nutrition_provider, None)


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
    # https, so the client keeps and sends the Secure session cookie like a browser would
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
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
