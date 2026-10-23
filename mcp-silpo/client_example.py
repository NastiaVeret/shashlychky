"""Приклад клієнта: те саме працює і з mock, і з реальним Сільпо — міняється лише URL.

    SILPO_MCP_URL=http://localhost:8000/mcp  uv run python client_example.py

Для реального сервера потрібна OAuth-авторизація (див. README), тут її немає.
"""
import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from silpo_client import SilpoClient

URL = os.environ.get("SILPO_MCP_URL", "http://localhost:8000/mcp")


async def main() -> None:
    async with streamablehttp_client(URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            silpo = SilpoClient(session)
            found = await silpo.find_products(["молоко 2.5%", "яйця"], limit=1)
            for query, products in found.items():
                top = products[0] if products else None
                print(query, "->", top and (top["name"], top["price"]))
            if all(found.values()):
                result = await silpo.add_products_verified([(found["яйця"][0], 1)])
                print("додано:", result.added, "не додано:", result.missing, "помилки:", result.errors)


asyncio.run(main())
