from httpx import AsyncClient

from app.schemas.recipes import Ingredient, RecipeContent
from tests.conftest import FakeCatalogProvider, FakeLLM, FakeNutrition

# One ingredient the user does not have: 3 eggs (Silpo sells them as "10шт" in the fake catalogue)
MISSING_EGGS_RECIPE = RecipeContent(
    title="Яєчня",
    description="Проста яєчня.",
    cooking_time_minutes=5,
    servings=1,
    ingredients=[Ingredient(name="Яйця", quantity=3, unit="шт", have_at_home=False)],
    steps=["Посмажити яйця."],
)


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


async def test_read_recipe_nutrition_returns_totals_and_goal(
    client: AsyncClient, fake_llm: FakeLLM, fake_nutrition: FakeNutrition, db_required: None
) -> None:
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()
    response = await client.get(
        f"/api/v1/recipes/{created['id']}/nutrition", params={"daily_kcal_goal": 2000}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"]["kcal"] == 30  # 1 tomato of 150 g at 20 kcal/100 g
    assert body["per_serving"]["kcal"] == 15
    assert body["counted_ingredients"] == 1
    assert body["countable_ingredients"] == 2
    assert body["goal"] == {"daily_kcal": 2000, "per_serving_percent": 0.8}
    # salt "за смаком" is not looked up
    assert fake_nutrition.calls == [["Яйця", "Помідор"]]


async def test_read_nutrition_of_missing_recipe_returns_404(
    client: AsyncClient, fake_nutrition: FakeNutrition, db_required: None
) -> None:
    response = await client.get("/api/v1/recipes/999999999/nutrition")
    assert response.status_code == 404


async def test_read_nutrition_with_unrealistic_goal_returns_422(
    client: AsyncClient, fake_nutrition: FakeNutrition
) -> None:
    response = await client.get("/api/v1/recipes/1/nutrition", params={"daily_kcal_goal": 50})
    assert response.status_code == 422
    assert fake_nutrition.calls == []


async def test_read_nutrition_without_silpo_returns_503(client: AsyncClient) -> None:
    response = await client.get("/api/v1/recipes/1/nutrition")
    assert response.status_code == 503
    assert "Сільпо" in response.json()["detail"]


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


async def test_anonymous_allergen_check_reports_what_silpo_declares(
    client: AsyncClient, fake_llm: FakeLLM, fake_catalog: FakeCatalogProvider, db_required: None
) -> None:
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/allergens")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["silpo_checked"] is True and body["profile_applied"] is False
    assert body["has_alerts"] is False
    rows = {r["name"]: r for r in body["ingredients"]}
    assert rows["Яйця"]["source"] == "declared"
    assert rows["Яйця"]["contains"] == ["яйця"] and rows["Яйця"]["traces"] == ["молоко"]
    assert rows["Яйця"]["product_url"] == "https://silpo.ua/product/p"
    # a card that says nothing is "unknown", and the user is pointed to the page to check
    assert rows["Помідор"]["source"] == "unknown"
    assert rows["Помідор"]["product_url"] == "https://silpo.ua/product/p"
    assert rows["Сіль"]["source"] == "unknown" and rows["Сіль"]["product_url"] is None
    assert body["unknown_ingredients"] == 2
    assert fake_catalog.calls == [["Яйця", "Помідор", "Сіль"]]  # one batch for the whole recipe


async def test_allergen_check_survives_silpo_being_down(
    client: AsyncClient, fake_llm: FakeLLM, down_catalog: FakeCatalogProvider, db_required: None
) -> None:
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/allergens")

    assert response.status_code == 200
    body = response.json()
    assert body["silpo_checked"] is False
    assert {r["source"] for r in body["ingredients"]} == {"unknown"}


async def test_allergen_check_of_missing_recipe_returns_404(
    client: AsyncClient, fake_catalog: FakeCatalogProvider, db_required: None
) -> None:
    response = await client.get("/api/v1/recipes/999999999/allergens")
    assert response.status_code == 404


async def test_shopping_list_skips_what_is_at_home_and_needs_no_silpo(
    client: AsyncClient, fake_llm: FakeLLM, fake_catalog: FakeCatalogProvider, db_required: None
) -> None:
    # SAMPLE_RECIPE: every ingredient is marked as already at home
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(line["name"], line["status"]) for line in body["lines"]] == [
        ("Яйця", "at_home"),
        ("Помідор", "at_home"),
        ("Сіль", "at_home"),
    ]
    assert body["total_price"] is None and body["needs_attention"] == 0
    assert fake_catalog.calls == []


async def test_shopping_list_when_silpo_is_down_returns_503(
    client: AsyncClient, fake_llm: FakeLLM, down_catalog: FakeCatalogProvider, db_required: None
) -> None:
    fake_llm.responses = [MISSING_EGGS_RECIPE]
    created = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.status_code == 503


async def test_shopping_list_prices_what_the_user_has_to_buy(
    client: AsyncClient, fake_llm: FakeLLM, fake_catalog: FakeCatalogProvider, db_required: None
) -> None:
    fake_llm.responses = [MISSING_EGGS_RECIPE]
    created = (await client.post("/api/v1/recipes", json={"products": ["борошно"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.status_code == 200, response.text
    (line,) = response.json()["lines"]
    assert line["status"] == "ok" and line["product"]["package"] == "10шт"
    assert line["purchase"]["quantity"] == 1 and line["purchase"]["total_price"] == 138.03
    assert response.json()["total_price"] == 138.03


async def test_shopping_list_of_missing_recipe_returns_404(
    client: AsyncClient, fake_catalog: FakeCatalogProvider, db_required: None
) -> None:
    assert (await client.get("/api/v1/recipes/999999999/shopping-list")).status_code == 404
