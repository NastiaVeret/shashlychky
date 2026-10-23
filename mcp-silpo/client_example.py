"""Приклад клієнта: те саме працює і з mock, і з реальним Сільпо — міняється лише URL.

    SILPO_MCP_URL=http://localhost:8000/mcp  uv run python client_example.py
"""
import asyncio
import json
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = os.environ.get("SILPO_MCP_URL", "http://localhost:8000/mcp")


async def call(session: ClientSession, name: str, args: dict | None = None) -> dict:
    result = await session.call_tool(name, args or {})
    return json.loads(result.content[0].text)


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            cart_id = (await call(session, "silpo_get_my_shopping_cart"))["shoppingCartId"]
            cart = (await call(session, "silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id}))["cart"]
            shipment = cart["shipments"][0]
            ctx = {"branchId": shipment["branchId"], "deliveryType": cart["deliveryType"],
                   "timeslotStart": cart["timeslot"]["start"], "timeslotEnd": cart["timeslot"]["end"]}
            found = await call(session, "silpo_find_products_batch",
                               {**ctx, "products": ["молоко 2.5%", "яйця"], "limit": 1})
            for q in found["queries"]:
                top = q["products"][0] if q["products"] else None
                print(q["query"], "->", top and (top["name"], top["price"]))


asyncio.run(main())
