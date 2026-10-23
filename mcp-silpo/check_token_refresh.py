"""Ручна перевірка: чи тихо оновлюється протухлий токен (без браузера) на РЕАЛЬНОМУ Сільпо.

Робить копію .silpo_tokens.json, ставить у ній `saved_at` так, ніби токен отримано давно й він спливув,
і підключається. Очікується: клієнт сам оновлює токен через refresh_token, браузер НЕ відкривається,
в файлі з'являється новий access_token. Нічого не пише в акаунт Сільпо (лише одне читання).
Якщо щось пішло не так, копію можна повернути: cp .silpo_tokens.json.bak .silpo_tokens.json

    uv run python check_token_refresh.py
"""
import asyncio
import json
import shutil
import time
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from silpo_auth import FileTokenStorage, make_auth

URL = "https://mcp.silpo.ua/mcp"
TOKENS = Path(".silpo_tokens.json")
BACKUP = Path(".silpo_tokens.json.bak")


async def browser_must_not_open(url: str) -> None:
    raise SystemExit(f"НЕ ПРОЙШЛО: клієнт спробував відкрити браузер (повний вхід) замість оновлення токена:\n{url}")


async def main() -> None:
    if not TOKENS.exists():
        raise SystemExit("Немає .silpo_tokens.json: спершу увійдіть (uv run python client_example.py з реальним URL)")
    shutil.copy(TOKENS, BACKUP)
    data = json.loads(TOKENS.read_text())
    old_access = data["tokens"]["access_token"]
    data["saved_at"] = time.time() - int(data["tokens"]["expires_in"]) - 60  # сплив хвилину тому
    TOKENS.write_text(json.dumps(data))
    print("токен позначено як протухлий, підключаюсь...")

    auth = make_auth(URL, FileTokenStorage(TOKENS), redirect_handler=browser_must_not_open)
    async with streamablehttp_client(URL, auth=auth) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("silpo_get_my_food_restrictions", {})
            print("відповідь сервера:", result.content[0].text[:120])

    new = json.loads(TOKENS.read_text())
    changed = new["tokens"]["access_token"] != old_access
    print("access_token змінився:", changed, "| saved_at оновлено:", new["saved_at"] > data["saved_at"] + 30)
    print("ПРОЙШЛО: токен оновлено без браузера" if changed else "НЕ ПРОЙШЛО: токен не змінився")
    print("(резервна копія: .silpo_tokens.json.bak, можна видалити)")


asyncio.run(main())
