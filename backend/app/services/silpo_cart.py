"""Putting shopping-list products into the user's own Silpo cart.

The cart belongs to the user's Silpo account, so every call runs on their login
(`DbTokenStorage.for_user`), never on the shared service account. Adding is a write: it is
never retried blindly (`SilpoClient` already refuses to repeat a cart write it could not read
back) and the result is what Silpo's cart holds afterwards, not what we asked for.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, Protocol

import httpx
from fastapi import Depends
from mcp.shared.exceptions import McpError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import (
    ProductDataUnavailableError,
    SilpoCartBlockedError,
    SilpoNotConnectedForCartError,
)
from app.db.session import get_sessionmaker
from app.integrations.silpo import (
    AddResult,
    NoDeliverySlotsError,
    NoStoreSelectedError,
    SilpoError,
    SilpoNotConnectedError,
    connect,
)
from app.integrations.silpo.db_storage import DbTokenStorage
from app.schemas.silpo import CartAddResult, CartItem
from app.services.silpo_connections import get_status

logger = logging.getLogger(__name__)

# One add is: read the cart, maybe move an expired delivery slot, add, read back, get the
# checkout link. Generous, but a stuck Silpo must still end in an answer.
CART_DEADLINE_SECONDS = 30.0

_SILPO_DOWN = (SilpoError, McpError, httpx.HTTPError, TimeoutError, OSError)

NO_ADDRESS = (
    "У вашому акаунті Сільпо не вибрано адресу доставки. "
    "Виберіть її в застосунку Сільпо й спробуйте ще раз."
)
NO_SLOTS = "Для вашої адреси зараз немає вільних слотів доставки Сільпо. Спробуйте пізніше."
# After a failed write we cannot tell whether Silpo applied it, so we do not say it did not.
NO_ANSWER = (
    "Сільпо не відповіло, тож ми не знаємо, чи товари потрапили в кошик. "
    "Перевірте кошик у Сільпо, перш ніж додавати знову."
)
NOTE_NOT_ADDED = "Частину товарів не додано: у вашому магазині їх немає або не вистачає."
NOTE_STOCK = "Сільпо позначило проблеми з наявністю. Перевірте кошик перед оформленням."
NOTE_MIN_ORDER = "Сума кошика поки менша за мінімальну для доставки, тож оформити його ще не можна."


class CartSession(Protocol):
    """The part of `SilpoClient` this module uses. Values are raw MCP JSON, hence Any."""

    async def cart(self) -> tuple[str, dict[str, Any]]: ...

    async def add_products_verified(
        self, items: list[tuple[dict[str, Any], float]]
    ) -> AddResult: ...

    async def checkout_links(self) -> dict[str, str | None]: ...


class CartProvider(Protocol):
    """Runs `work` on a Silpo session logged in as the user."""

    async def run[T](
        self, user_id: uuid.UUID, work: Callable[[CartSession], Awaitable[T]]
    ) -> T: ...


def _cause(exc: BaseException) -> BaseException:
    """The MCP SDK wraps errors from its task group in ExceptionGroups: find the one that matters.
    Account problems win over transport noise raised alongside them."""
    if not isinstance(exc, BaseExceptionGroup):
        return exc
    for wanted in (SilpoNotConnectedError, NoStoreSelectedError, NoDeliverySlotsError):
        found = exc.subgroup(wanted)
        if found is not None:
            return _cause(found.exceptions[0])
    return _cause(exc.exceptions[0])


class ConnectedCartProvider:
    def __init__(self, url: str) -> None:
        self._url = url

    async def run[T](self, user_id: uuid.UUID, work: Callable[[CartSession], Awaitable[T]]) -> T:
        storage = DbTokenStorage.for_user(get_sessionmaker(), user_id)
        try:
            async with asyncio.timeout(CART_DEADLINE_SECONDS):
                async with connect(self._url, storage, interactive=False) as silpo:
                    return await work(silpo)
        except BaseException as raised:
            if not isinstance(raised, Exception | BaseExceptionGroup):
                raise  # cancellation and friends are never swallowed
            cause = _cause(raised)
            if isinstance(cause, SilpoNotConnectedError):
                raise SilpoNotConnectedForCartError() from raised
            if isinstance(cause, NoStoreSelectedError):
                raise SilpoCartBlockedError(NO_ADDRESS) from raised
            if isinstance(cause, NoDeliverySlotsError):
                raise SilpoCartBlockedError(NO_SLOTS) from raised
            if isinstance(cause, _SILPO_DOWN):
                logger.warning("silpo cart call failed: %s: %s", type(cause).__name__, cause)
            else:
                logger.exception("silpo cart call failed on an unexpected error")
            raise ProductDataUnavailableError(NO_ANSWER) from raised


class UnconfiguredCartProvider:
    async def run[T](self, user_id: uuid.UUID, work: Callable[[CartSession], Awaitable[T]]) -> T:
        raise ProductDataUnavailableError("Сільпо не налаштовано (немає SILPO_MCP_URL)")


def get_cart_provider(settings: Annotated[Settings, Depends(get_settings)]) -> CartProvider:
    if not settings.silpo_mcp_url:
        return UnconfiguredCartProvider()
    return ConnectedCartProvider(settings.silpo_mcp_url)


CartDep = Annotated[CartProvider, Depends(get_cart_provider)]


def _store(cart: dict[str, Any]) -> dict[str, Any]:
    """The store the cart delivers from. A fresh account has none until an address is picked."""
    shipments = cart.get("shipments")
    if (
        not cart.get("deliveryType")
        or not isinstance(shipments, list)
        or not shipments
        or not isinstance(shipments[0], dict)
        or not shipments[0].get("branchId")
    ):
        raise NoStoreSelectedError()
    return shipments[0]


def _notes(result: AddResult) -> list[str]:
    notes = []
    if result.missing:
        notes.append(NOTE_NOT_ADDED)
    elif result.errors:
        notes.append(NOTE_STOCK)
    if result.checkout_issues:
        notes.append(NOTE_MIN_ORDER)
    return notes


async def add_to_cart(
    db: AsyncSession, provider: CartProvider, user_id: uuid.UUID, items: Sequence[CartItem]
) -> CartAddResult:
    """Adds the products to the user's Silpo cart and reports what the cart holds afterwards.

    The products come from a shopping list built in the user's store, so they are added to that
    same store (the cart's own company and branch). Raises 409 when the account is not connected
    or the cart cannot take products, 503 when Silpo does not answer.
    """
    # Checked here, before Silpo: an unconnected account would start an OAuth registration.
    if not (await get_status(db, user_id)).connected:
        raise SilpoNotConnectedForCartError()

    async def work(silpo: CartSession) -> CartAddResult:
        _, cart = await silpo.cart()
        store = _store(cart)
        result = await silpo.add_products_verified(
            [
                (
                    {
                        "id": item.product_id,
                        "companyId": store["companyId"],
                        "branchId": store["branchId"],
                    },
                    item.quantity,
                )
                for item in items
            ]
        )
        checkout_url = None
        if result.added and not result.checkout_issues:
            checkout_url = (await silpo.checkout_links()).get("web")
        return CartAddResult(
            added=result.added,
            not_added=result.missing,
            notes=_notes(result),
            checkout_url=checkout_url,
        )

    return await provider.run(user_id, work)
