from httpx import AsyncClient

from tests.conftest import FakeLLM, FakeNutrition


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
