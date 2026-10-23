"""Приклад клієнта: те саме працює і з mock, і з реальним Сільпо — міняється лише URL.

    SILPO_MCP_URL=http://localhost:8000/mcp  uv run python client_example.py

Для реального сервера при першому запуску відкриється браузер для входу (OAuth), токен збережеться у .silpo_tokens.json.
Запис у кошик у прикладі не робиться навмисно: на реальному сервері це змінило б чужий кошик.
"""
import asyncio
import os

from silpo_client import connect

URL = os.environ.get("SILPO_MCP_URL", "http://localhost:8000/mcp")


async def main() -> None:
    async with connect(URL) as silpo:
        found = await silpo.find_products(["молоко 2.5%", "яйця"], limit=1)
        for query, products in found.items():
            top = products[0] if products else None
            print(query, "->", top and (top["name"], top["price"]))


asyncio.run(main())
