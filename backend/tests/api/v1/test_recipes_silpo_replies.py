"""Silpo answering something unexpected: the real client and provider over a fake MCP session.

The shopping list needs Silpo, so it answers 503; the allergen check always answers, degraded to
the dictionary hints (`silpo_checked=false`). Neither ever ends in a 500.
"""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from httpx import AsyncClient
from mcp.types import TextContent

from app.integrations.silpo import client as silpo_client
from app.integrations.silpo.client import SilpoClient
from app.main import app
from app.schemas.recipes import Ingredient, RecipeContent
from app.services import catalog as catalog_service
from app.services.catalog import ConnectedCatalogProvider, get_catalog_provider
from tests.conftest import FakeLLM

# Mayonnaise is not at home, so both the shopping list and the allergen check look it up
MAYO_RECIPE = RecipeContent(
    title="Салат",
    description="Салат з майонезом.",
    cooking_time_minutes=5,
    servings=1,
    ingredients=[Ingredient(name="Майонез", quantity=100, unit="г", have_at_home=False)],
    steps=["Змішати."],
)
SLOT = {"start": "2026-11-10T10:00:00+00:00", "end": "2026-11-10T12:00:00+00:00"}
MAYO_HIT = {
    "id": "id-mayo",
    "name": "Майонез «Щедро»",
    "slug": "mayo",
    "available": True,
    "price": 50.0,
    "stock": 10,
    "weighted": False,
    "step": 1,
    "displayRatio": "300г",
}


class _Result:
    def __init__(self, payload: Any) -> None:
        self.content = [TextContent(type="text", text=json.dumps(payload))]
        self.isError = False


class FakeMcpSession:
    """Answers each tool with a fixed JSON value; `replies` overrides the healthy defaults."""

    def __init__(self, **replies: Any) -> None:
        self.replies: dict[str, Any] = {
            "silpo_get_my_shopping_cart": {"shoppingCartId": "cart-1"},
            "silpo_get_shopping_cart_by_id": {
                "cart": {"deliveryType": "DeliveryHome", "shipments": [{"branchId": "b"}]}
            },
            "silpo_get_time_slots": {"slots": [{**SLOT, "available": True}]},
            "silpo_find_products_batch": {
                "queries": [{"query": "Майонез", "products": [MAYO_HIT]}]
            },
            "silpo_get_product_details": {"product": {"url": "https://p", "attributes": {}}},
            "silpo_get_similar_products": {"products": []},
            **replies,
        }

    async def call_tool(self, name: str, args: dict[str, Any]) -> _Result:
        return _Result(self.replies[name])


@pytest.fixture
def silpo_replies(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeMcpSession]:
    session = FakeMcpSession()

    @asynccontextmanager
    async def fake_connect(*_: object, **__: object) -> AsyncIterator[SilpoClient]:
        yield SilpoClient(session)  # type: ignore[arg-type]

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(catalog_service, "connect", fake_connect)
    monkeypatch.setattr(catalog_service, "get_sessionmaker", lambda: None)
    monkeypatch.setattr(silpo_client.asyncio, "sleep", no_sleep)  # the non-JSON retry pause
    app.dependency_overrides[get_catalog_provider] = lambda: ConnectedCatalogProvider("https://x")
    yield session
    app.dependency_overrides.pop(get_catalog_provider, None)


async def _mayo_recipe(client: AsyncClient, fake_llm: FakeLLM) -> int:
    fake_llm.responses = [MAYO_RECIPE]
    created = await client.post("/api/v1/recipes", json={"products": ["майонез"]})
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


# A read tool answering with a JSON list or null, and a cart with no store: each breaks the lookup
BROKEN_REPLIES = [
    {"silpo_find_products_batch": [{"query": "Майонез"}]},
    {"silpo_find_products_batch": None},
    {"silpo_get_shopping_cart_by_id": {"cart": {"deliveryType": "DeliveryHome"}}},
    {"silpo_get_time_slots": ["not", "an", "object"]},
]


@pytest.mark.parametrize("replies", BROKEN_REPLIES)
async def test_shopping_list_on_a_broken_silpo_reply_returns_503(
    client: AsyncClient,
    fake_llm: FakeLLM,
    silpo_replies: FakeMcpSession,
    db_required: None,
    replies: dict[str, Any],
) -> None:
    recipe_id = await _mayo_recipe(client, fake_llm)
    silpo_replies.replies.update(replies)

    response = await client.get(f"/api/v1/recipes/{recipe_id}/shopping-list")

    assert response.status_code == 503, response.text


@pytest.mark.parametrize("replies", BROKEN_REPLIES)
async def test_allergen_check_on_a_broken_silpo_reply_is_degraded_not_500(
    client: AsyncClient,
    fake_llm: FakeLLM,
    silpo_replies: FakeMcpSession,
    db_required: None,
    replies: dict[str, Any],
) -> None:
    recipe_id = await _mayo_recipe(client, fake_llm)
    silpo_replies.replies.update(replies)

    response = await client.get(f"/api/v1/recipes/{recipe_id}/allergens")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["silpo_checked"] is False
    (row,) = body["ingredients"]
    assert row["source"] == "likely" and "яйця" in row["likely"]  # the dictionary still warns


async def test_a_card_that_is_a_json_list_is_read_as_an_empty_card(
    client: AsyncClient, fake_llm: FakeLLM, silpo_replies: FakeMcpSession, db_required: None
) -> None:
    recipe_id = await _mayo_recipe(client, fake_llm)
    silpo_replies.replies["silpo_get_product_details"] = [{"product": {}}]

    allergens = await client.get(f"/api/v1/recipes/{recipe_id}/allergens")
    shopping = await client.get(f"/api/v1/recipes/{recipe_id}/shopping-list")

    assert allergens.status_code == 200, allergens.text
    assert allergens.json()["silpo_checked"] is True
    (row,) = allergens.json()["ingredients"]
    assert row["product_url"] is None and row["source"] == "likely"
    assert shopping.status_code == 200, shopping.text
    assert shopping.json()["lines"][0]["status"] == "ok"


async def test_an_empty_pack_is_an_unknown_package_not_500(
    client: AsyncClient, fake_llm: FakeLLM, silpo_replies: FakeMcpSession, db_required: None
) -> None:
    recipe_id = await _mayo_recipe(client, fake_llm)
    empty = {**MAYO_HIT, "displayRatio": "0г"}
    silpo_replies.replies["silpo_find_products_batch"] = {
        "queries": [{"query": "Майонез", "products": [empty]}]
    }

    response = await client.get(f"/api/v1/recipes/{recipe_id}/shopping-list")

    assert response.status_code == 200, response.text
    assert response.json()["lines"][0]["status"] == "unknown_package"
