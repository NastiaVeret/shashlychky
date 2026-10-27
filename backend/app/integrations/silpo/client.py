"""Обгортка над MCP-сесією Сільпо: прибирає підводні камені реального сервера.

- контекст пошуку (branchId, deliveryType, слот) береться зі СВІЖОГО слота,
  а не зі слота кошика, який може бути в минулому (тоді stock усіх товарів = 0);
- слот у самому кошику оновлюється на найближчий доступний (ensure_valid_slot);
- додавання в кошик перевіряється перечитуванням кошика, бо сервер повертає
  success навіть коли товар не додався.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from mcp import ClientSession
from mcp.client.auth import TokenStorage
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError
from mcp.types import TextContent

from app.integrations.silpo.auth import make_auth

logger = logging.getLogger(__name__)

# A stuck Silpo call must not hold a backend request for the SDK's default 5 minutes.
CALL_TIMEOUT = timedelta(seconds=15)
SSE_READ_TIMEOUT = timedelta(seconds=60)


class SilpoError(RuntimeError):
    """Tool повернув помилку або не-JSON. Текст відповіді сервера зберігається в `.text`."""

    def __init__(self, tool: str, text: str):
        super().__init__(f"{tool}: {text[:300]}")
        self.tool, self.text = tool, text


class SilpoNotConnectedError(SilpoError):
    """No Silpo login on this deployment: run scripts/silpo_login.py --to-db once."""

    def __init__(self) -> None:
        super().__init__("auth", "Сільпо не підключено: потрібен одноразовий вхід")


class NoDeliverySlotsError(SilpoError):
    """The store has no available delivery slot, so nothing cart-related can proceed."""

    def __init__(self) -> None:
        super().__init__("silpo_get_time_slots", "Немає доступних слотів доставки")


RATE_LIMIT = re.compile(r"429|rate.?limit|too many|забагато", re.IGNORECASE)
RETRY_DELAYS = (1, 2, 4)  # секунди; експоненціальна пауза при ліміті запитів


async def _no_browser(url: str) -> None:
    raise SilpoNotConnectedError()


async def _no_callback() -> tuple[str, str | None]:
    raise SilpoNotConnectedError()


@asynccontextmanager
async def connect(
    url: str, storage: TokenStorage | None = None, *, interactive: bool = True
) -> AsyncIterator["SilpoClient"]:
    """Підключення до mock (localhost, без логіну) або до реального Сільпо (OAuth).

    async with connect(os.environ["SILPO_MCP_URL"]) as silpo:
        found = await silpo.find_products(["яйця"])

    `storage` keeps the OAuth tokens (file by default; the web service passes the DB storage).
    `interactive=False` never opens a browser: with no usable token it raises
    SilpoNotConnectedError instead of hanging on a login nobody can complete.
    """
    local = urlparse(url).hostname in ("localhost", "127.0.0.1")
    if local:
        auth = None
    elif interactive:
        auth = make_auth(url, storage)
    else:
        auth = make_auth(url, storage, redirect_handler=_no_browser, callback_handler=_no_callback)
    async with streamablehttp_client(
        url, auth=auth, timeout=CALL_TIMEOUT, sse_read_timeout=SSE_READ_TIMEOUT
    ) as (read, write, _):
        async with ClientSession(read, write, read_timeout_seconds=CALL_TIMEOUT) as session:
            await session.initialize()
            yield SilpoClient(session)


@dataclass
class AddResult:
    added: list[str]
    missing: list[str]  # productId, яких немає в кошику після додавання
    errors: list[dict]  # помилки самого додавання: слот, залишок товару тощо
    checkout_issues: list[
        dict
    ]  # помилки рівня замовлення, наприклад order.cost.min (мінімальна сума):
    #                              товар додано нормально, але оформити кошик поки не можна

    @property
    def ok(self) -> bool:
        return not self.missing and not self.errors


def _is_rate_limit(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429
    if isinstance(exc, McpError):
        return bool(RATE_LIMIT.search(exc.error.message))
    return False


def _text(result: object) -> str:
    content = getattr(result, "content", None) or []
    return "".join(c.text for c in content if isinstance(c, TextContent))


class SilpoClient:
    def __init__(self, session: ClientSession):
        self.session = session
        self._cart_id: str | None = None  # stable per user; fetched once

    async def call(self, name: str, args: dict | None = None) -> dict:
        """Викликає tool і розбирає JSON. При ліміті запитів (429) повторює з паузою 1/2/4 с.
        Ліміт розпізнається за текстом і в відповіді tool'а, і у винятку (як саме його віддає
        реальний сервер, невідомо). Решта винятків і помилок пробиваються одразу."""
        for delay in (*RETRY_DELAYS, None):
            try:
                result = await self.session.call_tool(name, args or {})
            except (McpError, httpx.HTTPStatusError) as e:
                if delay is not None and _is_rate_limit(e):
                    logger.warning("silpo rate limited on %s, retrying in %ss", name, delay)
                    await asyncio.sleep(delay)
                    continue
                raise
            text = _text(result)
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
            if data is not None and not result.isError:
                return data
            if delay is not None and RATE_LIMIT.search(text):
                await asyncio.sleep(delay)
                continue
            raise SilpoError(name, text)
        raise AssertionError("unreachable: the retry loop returns or raises")

    async def cart_id(self) -> str:
        if self._cart_id is None:
            self._cart_id = (await self.call("silpo_get_my_shopping_cart"))["shoppingCartId"]
        return self._cart_id

    async def cart(self) -> tuple[str, dict]:
        cart_id = await self.cart_id()
        cart = (await self.call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id}))[
            "cart"
        ]
        return cart_id, cart

    async def search_context(self) -> dict:
        """branchId + deliveryType з кошика, слот - найближчий доступний."""
        _, cart = await self.cart()
        branch_id = cart["shipments"][0]["branchId"]
        delivery_type = cart["deliveryType"]
        slots = await self.call(
            "silpo_get_time_slots",
            {
                "branchId": branch_id,
                "deliveryTypes": [delivery_type],
                "start": datetime.now(UTC).isoformat(),
                "limit": 10,
            },
        )
        slot = next((s for s in slots["slots"] if s["available"]), None)
        if slot is None:
            raise NoDeliverySlotsError()
        return {
            "branchId": branch_id,
            "deliveryType": delivery_type,
            "timeslotStart": slot["start"],
            "timeslotEnd": slot["end"],
        }

    async def ensure_valid_slot(self) -> bool:
        """Гарантує, що слот КОШИКА дійсний (слот кошика швидко протухає, і тоді
        Сільпо рахує кошик невалідним: timeslot.not_found і stock 0 в усіх товарів).

        Адреса, магазин і тип доставки лишаються користувача, змінюється лише вікно:
        на найближче доступне. Нічого не пише, якщо слот і так дійсний. Повертає True,
        якщо після цього в кошику немає помилки слота.
        """
        cart_id, cart = await self.cart()
        delivery_type = cart["deliveryType"]
        shipment = cart["shipments"][0]
        # для експрес-доставки слоти запитуються як для звичайної (за описом tool'а)
        slot_type = "DeliveryHome" if delivery_type == "DeliveryExpressByPromise" else delivery_type
        slots = await self.call(
            "silpo_get_time_slots",
            {
                "branchId": shipment["branchId"],
                "deliveryTypes": [slot_type],
                "start": datetime.now(UTC).isoformat(),
                "limit": 10,
            },
        )
        available = [s for s in slots["slots"] if s["available"]]
        if not available:
            raise NoDeliverySlotsError()

        def same(a: str, b: str) -> bool:
            return datetime.fromisoformat(a) == datetime.fromisoformat(b)

        current = cart.get("timeslot") or {}
        if current and any(
            same(current["start"], s["start"]) and same(current["end"], s["end"]) for s in available
        ):
            return True
        await self.call(
            "silpo_update_shopping_cart",
            {
                "shoppingCartId": cart_id,
                "deliveryType": delivery_type,
                "timeslot": {"start": available[0]["start"], "end": available[0]["end"]},
                "address": cart["address"],  # точно як у кошику, за вимогою tool'а
                "shipments": [
                    {"companyId": shipment["companyId"], "branchId": shipment["branchId"]}
                ],
            },
        )
        _, cart = await self.cart()
        return not any(
            v["type"] == "timeslot" and v["level"] == "error"
            for v in cart["calculation"]["validations"]
        )

    async def find_products(self, names: list[str], limit: int = 3) -> dict[str, list[dict]]:
        ctx = await self.search_context()
        found = await self.call(
            "silpo_find_products_batch", {**ctx, "products": names, "limit": limit}
        )
        return {q["query"]: q["products"] for q in found["queries"]}

    async def add_products_verified(self, items: list[tuple[dict, float]]) -> AddResult:
        """items: [(товар з пошуку, кількість)]. Для вагових товарів кількість у кг."""
        await self.ensure_valid_slot()
        cart_id = await self.cart_id()
        await self.call(
            "silpo_add_cart_products",
            {
                "shoppingCartId": cart_id,
                "products": [
                    {
                        "productId": p["id"],
                        "companyId": p["companyId"],
                        "branchId": p["branchId"],
                        "quantity": q,
                    }
                    for p, q in items
                ],
            },
        )
        _, cart = await self.cart()
        in_cart = {l["productId"] for s in cart["shipments"] for l in s["products"]}
        wanted = [p["id"] for p, _ in items]
        problems = [v for v in cart["calculation"]["validations"] if v["level"] == "error"]
        return AddResult(
            added=[i for i in wanted if i in in_cart],
            missing=[i for i in wanted if i not in in_cart],
            errors=[v for v in problems if v["type"] != "order"],
            checkout_issues=[v for v in problems if v["type"] == "order"],
        )

    async def _lines(self) -> dict[str, dict]:
        """productId -> рядок кошика (з id рядка, потрібним для update/remove)."""
        _, cart = await self.cart()
        return {l["productId"]: l for s in cart["shipments"] for l in s["products"]}

    async def set_quantity(self, product_id: str, quantity: float) -> bool:
        """Нова АБСОЛЮТНА кількість товару, що вже в кошику. True, якщо зміна застосувалась."""
        line = (await self._lines()).get(product_id)
        if line is None:
            return False
        cart_id = await self.cart_id()
        await self.call(
            "silpo_update_cart_products",
            {"shoppingCartId": cart_id, "products": [{"id": line["id"], "quantity": quantity}]},
        )
        return (await self._lines()).get(product_id, {}).get("quantity") == quantity

    async def remove_products(self, product_ids: list[str]) -> list[str]:
        """Видаляє товари за productId. Повертає ті, що лишились у кошику (мало бути порожньо)."""
        lines = await self._lines()
        ids = [{"id": lines[p]["id"]} for p in product_ids if p in lines]
        if ids:
            cart_id = await self.cart_id()
            await self.call(
                "silpo_remove_cart_products", {"shoppingCartId": cart_id, "products": ids}
            )
        after = await self._lines()
        return [p for p in product_ids if p in after]

    async def similar_products(self, product: dict, limit: int = 5) -> list[dict]:
        """Альтернативи товару (F10). Беруться з того самого свіжого контексту."""
        ctx = await self.search_context()
        res = await self.call(
            "silpo_get_similar_products", {**ctx, "slug": product["slug"], "limit": limit}
        )
        return res.get("products", [])

    async def food_restrictions(self) -> list:
        return (await self.call("silpo_get_my_food_restrictions")).get("restrictions", [])

    async def checkout_links(self) -> dict[str, str | None]:
        """Посилання на оформлення в Сільпо (оплата й доставка на їхньому боці).
        Слот оновлюється прямо перед видачею, бо за час між складанням кошика й оформленням він міг протухнути.
        Посилання з'являються лише для кошика, який можна оформити (сума не нижча за мінімальну)."""
        await self.ensure_valid_slot()
        cart_id = await self.cart_id()
        res = await self.call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id})
        cart = res.get("cart", {})
        return {
            "web": res.get("checkoutWebLink") or cart.get("checkoutWebLink"),
            "mobile": res.get("checkoutMobileLink") or cart.get("checkoutMobileLink"),
        }
