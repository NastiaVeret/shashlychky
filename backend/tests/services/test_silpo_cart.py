"""Adding to the user's Silpo cart: what goes in, what comes back, how Silpo failures read."""

import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.core.errors import (
    ProductDataUnavailableError,
    SilpoCartBlockedError,
    SilpoNotConnectedForCartError,
)
from app.integrations.silpo import (
    AddResult,
    NoDeliverySlotsError,
    NoStoreSelectedError,
    SilpoNotConnectedError,
)
from app.schemas.silpo import CartItem, SilpoConnectionRead
from app.services import silpo_cart
from app.services.silpo_cart import (
    NO_ADDRESS,
    NO_ANSWER,
    NO_SLOTS,
    NOTE_MIN_ORDER,
    NOTE_NOT_ADDED,
    NOTE_STOCK,
    CartSession,
    ConnectedCartProvider,
    add_to_cart,
)

USER = uuid.uuid4()
STORE = {"companyId": "company-1", "branchId": "branch-1", "products": []}
CART = {"deliveryType": "DeliveryHome", "shipments": [STORE]}
CHECKOUT = "https://silpo.ua/checkout/cart-1"


class FakeCart:
    def __init__(self, result: AddResult, cart: dict[str, Any] | None = None) -> None:
        self.result = result
        self.cart_payload = CART if cart is None else cart
        self.added: list[tuple[dict[str, Any], float]] = []
        self.checkout_asked = False

    async def cart(self) -> tuple[str, dict[str, Any]]:
        return "cart-1", self.cart_payload

    async def add_products_verified(self, items: list[tuple[dict[str, Any], float]]) -> AddResult:
        self.added = items
        return self.result

    async def checkout_links(self) -> dict[str, str | None]:
        self.checkout_asked = True
        return {"web": CHECKOUT, "mobile": None}


class DirectProvider:
    """Runs the work on the fake as is: no session, no error mapping."""

    def __init__(self, fake: FakeCart) -> None:
        self.fake = fake
        self.users: list[uuid.UUID] = []

    async def run[T](self, user_id: uuid.UUID, work: Callable[[CartSession], Awaitable[T]]) -> T:
        self.users.append(user_id)
        return await work(self.fake)


def result(**fields: list[Any]) -> AddResult:
    base: dict[str, list[Any]] = {"added": [], "missing": [], "errors": [], "checkout_issues": []}
    return AddResult(**{**base, **fields})


@pytest.fixture
def connected(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    state = [True]

    async def status(db: object, user_id: uuid.UUID) -> SilpoConnectionRead:
        return SilpoConnectionRead(connected=state[0])

    monkeypatch.setattr(silpo_cart, "get_status", status)
    return state


ITEMS = [CartItem(product_id="p1", quantity=2), CartItem(product_id="p2", quantity=0.5)]


async def test_products_go_to_the_carts_own_store(connected: list[bool]) -> None:
    fake = FakeCart(result(added=["p1", "p2"]))
    provider = DirectProvider(fake)

    answer = await add_to_cart(None, provider, USER, ITEMS)  # type: ignore[arg-type]

    assert provider.users == [USER]
    assert fake.added == [
        ({"id": "p1", "companyId": "company-1", "branchId": "branch-1"}, 2),
        ({"id": "p2", "companyId": "company-1", "branchId": "branch-1"}, 0.5),
    ]
    assert answer.added == ["p1", "p2"] and answer.not_added == [] and answer.notes == []
    assert answer.checkout_url == CHECKOUT


async def test_products_missing_after_adding_are_reported(connected: list[bool]) -> None:
    fake = FakeCart(result(added=["p1"], missing=["p2"]))

    answer = await add_to_cart(None, DirectProvider(fake), USER, ITEMS)  # type: ignore[arg-type]

    assert answer.added == ["p1"] and answer.not_added == ["p2"]
    assert answer.notes == [NOTE_NOT_ADDED]


async def test_stock_problems_of_added_products_are_a_note(connected: list[bool]) -> None:
    fake = FakeCart(result(added=["p1", "p2"], errors=[{"type": "stock", "level": "error"}]))

    answer = await add_to_cart(None, DirectProvider(fake), USER, ITEMS)  # type: ignore[arg-type]

    assert answer.notes == [NOTE_STOCK]


async def test_below_minimum_order_gives_no_checkout_link(connected: list[bool]) -> None:
    fake = FakeCart(result(added=["p1", "p2"], checkout_issues=[{"type": "order"}]))

    answer = await add_to_cart(None, DirectProvider(fake), USER, ITEMS)  # type: ignore[arg-type]

    assert answer.notes == [NOTE_MIN_ORDER]
    assert answer.checkout_url is None and not fake.checkout_asked


async def test_cart_without_store_adds_nothing(connected: list[bool]) -> None:
    fake = FakeCart(result(), cart={"deliveryType": None, "shipments": []})

    with pytest.raises(NoStoreSelectedError):
        await add_to_cart(None, DirectProvider(fake), USER, ITEMS)  # type: ignore[arg-type]
    assert fake.added == []


async def test_unconnected_user_never_reaches_silpo(connected: list[bool]) -> None:
    connected[0] = False
    provider = DirectProvider(FakeCart(result()))

    with pytest.raises(SilpoNotConnectedForCartError):
        await add_to_cart(None, provider, USER, ITEMS)  # type: ignore[arg-type]
    assert provider.users == []


# ---------- ConnectedCartProvider: how Silpo failures read to the user ----------


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> list[BaseException]:
    """The session raises what the test puts in the list, wrapped like the MCP SDK does."""
    raised: list[BaseException] = []

    @asynccontextmanager
    async def fake_connect(*_: object, **__: object):  # type: ignore[no-untyped-def]
        if raised:
            raise ExceptionGroup("unhandled errors in a TaskGroup", [raised[0]])
        yield FakeCart(result(added=["p1"]))

    monkeypatch.setattr(silpo_cart, "connect", fake_connect)
    monkeypatch.setattr(silpo_cart, "get_sessionmaker", lambda: None)
    return raised


async def _run() -> list[str]:
    async def work(cart: CartSession) -> list[str]:
        return (await cart.add_products_verified([])).added

    return await ConnectedCartProvider("https://x").run(USER, work)


async def test_provider_runs_the_work_on_the_users_session(session: list[BaseException]) -> None:
    assert await _run() == ["p1"]


@pytest.mark.parametrize(
    ("cause", "error", "detail"),
    [
        (SilpoNotConnectedError(), SilpoNotConnectedForCartError, None),
        (NoStoreSelectedError(), SilpoCartBlockedError, NO_ADDRESS),
        (NoDeliverySlotsError(), SilpoCartBlockedError, NO_SLOTS),
        (httpx.ConnectError("down"), ProductDataUnavailableError, NO_ANSWER),
    ],
)
async def test_provider_turns_silpo_failures_into_clear_errors(
    session: list[BaseException], cause: BaseException, error: type[Exception], detail: str | None
) -> None:
    session.append(cause)

    with pytest.raises(error) as caught:
        await _run()
    if detail is not None:
        assert caught.value.detail == detail  # type: ignore[attr-defined]
