import pytest
from httpx import AsyncClient

from app.schemas.recipes import Ingredient, RecipeContent
from tests.api.v1.test_auth import register, unique_email
from tests.conftest import SAMPLE_RECIPE, FakeLLM

# SAMPLE_RECIPE (the FakeLLM default) is an omelette with eggs, tomato and salt.
EGG_FREE_RECIPE = RecipeContent(
    title="Салат з помідорів",
    description="Свіжий салат.",
    cooking_time_minutes=5,
    servings=2,
    ingredients=[Ingredient(name="Помідор", quantity=2, unit="шт", have_at_home=True)],
    steps=["Нарізати помідори.", "Посолити."],
)


@pytest.fixture
async def logged_in(client: AsyncClient, db_required: None) -> None:
    assert (await register(client, unique_email())).status_code == 201


async def save_profile(client: AsyncClient, **fields: object) -> None:
    response = await client.put("/api/v1/me/profile", json=fields)
    assert response.status_code == 200, response.text


async def test_recipe_of_logged_in_user_uses_profile_and_is_listed(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    await save_profile(client, diets=["vegetarian"], pantry=["рис"])

    created = await client.post("/api/v1/recipes", json={"products": ["помідор"]})

    assert created.status_code == 201, created.text
    prompt = fake_llm.calls[0]["user"]
    assert "Профіль користувача" in prompt
    assert "вегетаріанське" in prompt
    assert "Базові запаси, завжди є вдома: рис" in prompt
    mine = await client.get("/api/v1/me/recipes")
    assert mine.status_code == 200
    assert [r["id"] for r in mine.json()] == [created.json()["id"]]


async def test_next_recipe_prompt_lists_recent_titles(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    await client.post("/api/v1/recipes", json={"products": ["яйця"]})

    await client.post("/api/v1/recipes", json={"products": ["яйця"]})

    assert "Нещодавно" not in fake_llm.calls[0]["user"]
    assert f"не повторюй:\n- {SAMPLE_RECIPE.title}" in fake_llm.calls[1]["user"]


async def test_anonymous_recipe_ignores_profiles_and_is_not_listed(
    client: AsyncClient, fake_llm: FakeLLM, db_required: None
) -> None:
    created = await client.post("/api/v1/recipes", json={"products": ["яйця"]})

    assert created.status_code == 201
    assert "Профіль" not in fake_llm.calls[0]["user"]
    assert (await client.get("/api/v1/me/recipes")).status_code == 401


async def test_allergen_in_products_returns_422_without_calling_llm(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    await save_profile(client, allergies=["яйця"])

    response = await client.post("/api/v1/recipes", json={"products": ["Яйце", "помідор"]})

    assert response.status_code == 422
    assert "алерген" in response.json()["detail"]
    assert fake_llm.calls == []


async def test_recipe_with_allergen_is_regenerated(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    await save_profile(client, allergies=["яйця"])
    fake_llm.responses = [SAMPLE_RECIPE, EGG_FREE_RECIPE]

    response = await client.post("/api/v1/recipes", json={"products": ["помідор"]})

    assert response.status_code == 201, response.text
    assert response.json()["title"] == EGG_FREE_RECIPE.title
    assert len(fake_llm.calls) == 2
    assert "містив заборонені алергени (яйця)" in fake_llm.calls[1]["user"]


async def test_recipe_still_with_allergen_after_retry_returns_502(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    await save_profile(client, allergies=["яйця"])

    response = await client.post("/api/v1/recipes", json={"products": ["помідор"]})

    assert response.status_code == 502
    assert "без ваших алергенів" in response.json()["detail"]
    assert len(fake_llm.calls) == 2
    assert (await client.get("/api/v1/me/recipes")).json() == []  # nothing unsafe was stored


async def test_my_recipes_are_newest_first_and_paginated(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    ids = [
        (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()["id"]
        for _ in range(3)
    ]

    page = await client.get("/api/v1/me/recipes", params={"limit": 2, "offset": 1})

    assert [r["id"] for r in page.json()] == [ids[1], ids[0]]


async def test_my_recipes_limit_over_max_returns_422(client: AsyncClient, logged_in: None) -> None:
    response = await client.get("/api/v1/me/recipes", params={"limit": 51})

    assert response.status_code == 422


async def test_deleting_account_deletes_its_recipes(
    client: AsyncClient, fake_llm: FakeLLM, logged_in: None
) -> None:
    recipe_id = (await client.post("/api/v1/recipes", json={"products": ["яйця"]})).json()["id"]

    assert (await client.delete("/api/v1/me")).status_code == 204

    assert (await client.get(f"/api/v1/recipes/{recipe_id}")).status_code == 404
