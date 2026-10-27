from httpx import AsyncClient

from tests.conftest import FakeLLM


async def test_create_recipe_returns_201_and_stored_recipe(
    client: AsyncClient, fake_llm: FakeLLM, db_required: None
) -> None:
    response = await client.post(
        "/api/v1/recipes",
        json={"products": ["яйця", "помідор", " яйця "], "servings": 2},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Омлет з помідорами"
    assert body["products"] == ["яйця", "помідор"]  # trimmed and de-duplicated
    assert len(body["ingredients"]) == 3
    assert body["ingredients"][0]["have_at_home"] is True
    assert body["ingredients"][0]["unit"] == "шт"
    assert body["id"] > 0
    # the prompt carries the products and the servings, and the system prompt is separate
    assert "- яйця" in fake_llm.calls[0]["user"]
    assert "Порцій: 2" in fake_llm.calls[0]["user"]
    assert "кухар" in fake_llm.calls[0]["system"]


async def test_read_recipe_returns_same_payload(
    client: AsyncClient, fake_llm: FakeLLM, db_required: None
) -> None:
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()
    response = await client.get(f"/api/v1/recipes/{created['id']}")
    assert response.status_code == 200
    assert response.json() == created


async def test_read_missing_recipe_returns_404(client: AsyncClient, db_required: None) -> None:
    response = await client.get("/api/v1/recipes/999999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Рецепт не знайдено"


async def test_create_recipe_without_products_returns_422(
    client: AsyncClient, fake_llm: FakeLLM
) -> None:
    response = await client.post("/api/v1/recipes", json={"products": []})
    assert response.status_code == 422
    assert fake_llm.calls == []


async def test_create_recipe_with_only_blank_products_returns_422(
    client: AsyncClient, fake_llm: FakeLLM
) -> None:
    response = await client.post("/api/v1/recipes", json={"products": ["  ", ""]})
    assert response.status_code == 422


async def test_create_recipe_when_llm_down_returns_503(
    client: AsyncClient, failing_llm: FakeLLM
) -> None:
    response = await client.post("/api/v1/recipes", json={"products": ["яйця"]})
    assert response.status_code == 503
    assert "тимчасово недоступний" in response.json()["detail"]


async def test_read_legacy_recipe_row_returns_200(client: AsyncClient, db_required: None) -> None:
    """A recipe saved before the strict unit schema must stay readable via its share link."""
    from app.db.session import get_sessionmaker
    from app.models.recipe import Recipe

    legacy_content = {
        "title": "Грінки з часником",
        "description": "Хрусткий хліб. " * 25,
        "cooking_time_minutes": 15,
        "servings": 2,
        "ingredients": [
            {"name": "Часник", "quantity": 2, "unit": "зубчики", "have_at_home": True},
            {"name": "Хліб", "quantity": 4, "unit": "скибочки", "have_at_home": True},
        ],
        "steps": ["Натерти хліб часником.", "Підсмажити."],
        "tips": None,
        "clarifying_question": None,
    }
    async with get_sessionmaker()() as db:
        row = Recipe(
            products=["хліб", "часник"],
            preferences=None,
            servings=2,
            model="legacy-test",
            content=legacy_content,
            prompt_tokens=None,
            output_tokens=None,
            latency_ms=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

    response = await client.get(f"/api/v1/recipes/{row.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ingredients"][0]["unit"] == "зубчики"
    assert body["ingredients"][1]["unit"] == "скибочки"
