"""POST /api/v1/silpo/cart and the shopping list searched in the user's own Silpo store."""

import uuid
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from mcp.shared.auth import OAuthToken

from app.core.errors import SilpoAccountUnusableError
from app.db.session import get_sessionmaker
from app.integrations.silpo import AddResult
from app.integrations.silpo.catalog import ProductCatalog
from app.integrations.silpo.db_storage import DbTokenStorage
from app.main import app
from app.services.catalog import get_user_catalog_factory
from app.services.silpo_cart import CartSession, get_cart_provider
from tests.api.v1.test_auth import register, unique_email
from tests.api.v1.test_recipes import MISSING_EGGS_RECIPE
from tests.conftest import SAMPLE_MATCHES, FakeCatalogProvider, FakeLLM

CART = "/api/v1/silpo/cart"
ITEMS = {"items": [{"product_id": "p1", "quantity": 2}]}


class FakeCart:
    async def cart(self) -> tuple[str, dict[str, Any]]:
        store = {"companyId": "c", "branchId": "b", "products": []}
        return "cart-1", {"deliveryType": "DeliveryHome", "shipments": [store]}

    async def add_products_verified(self, items: list[tuple[dict[str, Any], float]]) -> AddResult:
        return AddResult(
            added=[p["id"] for p, _ in items], missing=[], errors=[], checkout_issues=[]
        )

    async def checkout_links(self) -> dict[str, str | None]:
        return {"web": "https://silpo.ua/checkout", "mobile": None}


class FakeCartProvider:
    def __init__(self) -> None:
        self.users: list[uuid.UUID] = []

    async def run[T](self, user_id: uuid.UUID, work: Callable[[CartSession], Awaitable[T]]) -> T:
        self.users.append(user_id)
        return await work(FakeCart())


@pytest.fixture
def fake_cart() -> Iterator[FakeCartProvider]:
    provider = FakeCartProvider()
    app.dependency_overrides[get_cart_provider] = lambda: provider
    yield provider
    app.dependency_overrides.pop(get_cart_provider, None)


async def log_in(client: AsyncClient) -> uuid.UUID:
    response = await register(client, unique_email())
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def connect_silpo(user_id: uuid.UUID) -> None:
    storage = DbTokenStorage.for_user(get_sessionmaker(), user_id)
    await storage.set_tokens(OAuthToken(access_token="A", token_type="Bearer", expires_in=3600))


async def test_add_to_cart_requires_login(client: AsyncClient, fake_cart: FakeCartProvider) -> None:
    assert (await client.post(CART, json=ITEMS)).status_code == 401
    assert fake_cart.users == []


async def test_add_to_cart_without_silpo_connected_returns_409(
    client: AsyncClient, fake_cart: FakeCartProvider, db_required: None
) -> None:
    await log_in(client)

    response = await client.post(CART, json=ITEMS)

    assert response.status_code == 409
    assert "Підключіть акаунт Сільпо" in response.json()["detail"]
    assert fake_cart.users == []


async def test_add_to_cart_returns_what_the_cart_holds(
    client: AsyncClient, fake_cart: FakeCartProvider, db_required: None
) -> None:
    user_id = await log_in(client)
    await connect_silpo(user_id)

    response = await client.post(CART, json=ITEMS)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "added": ["p1"],
        "not_added": [],
        "notes": [],
        "checkout_url": "https://silpo.ua/checkout",
    }
    assert fake_cart.users == [user_id]


@pytest.mark.parametrize(
    "body",
    [
        {"items": []},
        {"items": [{"product_id": "p1", "quantity": 0}]},
        {"items": [{"product_id": "p1", "quantity": 1}, {"product_id": "p1", "quantity": 2}]},
    ],
)
async def test_add_to_cart_rejects_bad_items(
    client: AsyncClient, fake_cart: FakeCartProvider, db_required: None, body: dict[str, Any]
) -> None:
    await log_in(client)

    assert (await client.post(CART, json=body)).status_code == 422


# ---------- the shopping list in the user's own store ----------


class UnusableAccount:
    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        raise SilpoAccountUnusableError()


@pytest.fixture
def own_store() -> Iterator[list[Any]]:
    """What the user's own account answers; set the first item to swap the provider."""
    provider: list[Any] = [FakeCatalogProvider(SAMPLE_MATCHES)]
    app.dependency_overrides[get_user_catalog_factory] = lambda: lambda user_id: provider[0]
    yield provider
    app.dependency_overrides.pop(get_user_catalog_factory, None)


async def test_shopping_list_of_connected_user_is_priced_in_their_store(
    client: AsyncClient,
    fake_llm: FakeLLM,
    fake_catalog: FakeCatalogProvider,
    own_store: list[Any],
    db_required: None,
) -> None:
    await connect_silpo(await log_in(client))
    fake_llm.responses = [MISSING_EGGS_RECIPE]
    created = (await client.post("/api/v1/recipes", json={"products": ["борошно"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.status_code == 200, response.text
    assert response.json()["priced_in"] == "your_store"
    assert own_store[0].calls and fake_catalog.calls == []


async def test_shopping_list_falls_back_when_the_users_account_is_unusable(
    client: AsyncClient,
    fake_llm: FakeLLM,
    fake_catalog: FakeCatalogProvider,
    own_store: list[Any],
    db_required: None,
) -> None:
    await connect_silpo(await log_in(client))
    own_store[0] = UnusableAccount()
    fake_llm.responses = [MISSING_EGGS_RECIPE]
    created = (await client.post("/api/v1/recipes", json={"products": ["борошно"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.status_code == 200, response.text
    assert response.json()["priced_in"] == "default_store"
    assert fake_catalog.calls


async def test_shopping_list_of_unconnected_user_uses_the_shared_store(
    client: AsyncClient,
    fake_llm: FakeLLM,
    fake_catalog: FakeCatalogProvider,
    own_store: list[Any],
    db_required: None,
) -> None:
    await log_in(client)
    fake_llm.responses = [MISSING_EGGS_RECIPE]
    created = (await client.post("/api/v1/recipes", json={"products": ["борошно"]})).json()

    response = await client.get(f"/api/v1/recipes/{created['id']}/shopping-list")

    assert response.json()["priced_in"] == "default_store"
    assert own_store[0].calls == []
