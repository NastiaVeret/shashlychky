"""Обгортка над MCP-сесією Сільпо: прибирає підводні камені реального сервера.

- контекст пошуку (branchId, deliveryType, слот) береться зі СВІЖОГО слота,
  а не зі слота кошика, який може бути в минулому (тоді stock усіх товарів = 0);
- додавання в кошик перевіряється перечитуванням кошика, бо сервер повертає
  success навіть коли товар не додався.
"""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from mcp import ClientSession


@dataclass
class AddResult:
    added: list[str]
    missing: list[str]  # productId, яких немає в кошику після додавання
    errors: list[dict]  # error-level validations[] з кошика

    @property
    def ok(self) -> bool:
        return not self.missing and not self.errors


class SilpoClient:
    def __init__(self, session: ClientSession):
        self.session = session

    async def call(self, name: str, args: dict | None = None) -> dict:
        result = await self.session.call_tool(name, args or {})
        return json.loads(result.content[0].text)

    async def cart(self) -> tuple[str, dict]:
        cart_id = (await self.call("silpo_get_my_shopping_cart"))["shoppingCartId"]
        cart = (await self.call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id}))["cart"]
        return cart_id, cart

    async def search_context(self) -> dict:
        """branchId + deliveryType з кошика, слот - найближчий доступний."""
        _, cart = await self.cart()
        branch_id = cart["shipments"][0]["branchId"]
        delivery_type = cart["deliveryType"]
        slots = await self.call("silpo_get_time_slots", {
            "branchId": branch_id, "deliveryTypes": [delivery_type],
            "start": datetime.now(timezone.utc).isoformat(), "limit": 10})
        slot = next((s for s in slots["slots"] if s["available"]), None)
        if slot is None:
            raise RuntimeError("Немає доступних слотів доставки")
        return {"branchId": branch_id, "deliveryType": delivery_type,
                "timeslotStart": slot["start"], "timeslotEnd": slot["end"]}

    async def find_products(self, names: list[str], limit: int = 3) -> dict[str, list[dict]]:
        ctx = await self.search_context()
        found = await self.call("silpo_find_products_batch", {**ctx, "products": names, "limit": limit})
        return {q["query"]: q["products"] for q in found["queries"]}

    async def add_products_verified(self, items: list[tuple[dict, float]]) -> AddResult:
        """items: [(товар з пошуку, кількість)]. Для вагових товарів кількість у кг."""
        cart_id, _ = await self.cart()
        await self.call("silpo_add_cart_products", {"shoppingCartId": cart_id, "products": [
            {"productId": p["id"], "companyId": p["companyId"], "branchId": p["branchId"], "quantity": q}
            for p, q in items]})
        _, cart = await self.cart()
        in_cart = {l["productId"] for s in cart["shipments"] for l in s["products"]}
        wanted = [p["id"] for p, _ in items]
        errors = [v for v in cart["calculation"]["validations"] if v["level"] == "error"]
        return AddResult(added=[i for i in wanted if i in in_cart],
                         missing=[i for i in wanted if i not in in_cart], errors=errors)
