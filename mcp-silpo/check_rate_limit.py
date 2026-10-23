"""Ручна перевірка: як реальний Сільпо відповідає на забагато запитів (429).

Не автотест. Шле короткі читальні запити хвилями (1, 5, 10, 20, 40 одночасних) і ЗУПИНЯЄТЬСЯ на першій
помилці, друкуючи її точний вигляд: тип винятку й текст. Це потрібно, щоб налаштувати розпізнавання
ліміту в SilpoClient.call (RATE_LIMIT), яке поки написане навмання.

Безпечність:
- не більше 76 запитів, пауза між хвилями;
- викликається `silpo_get_my_food_restrictions`: не читає каталог і не збирає ціни
  (умови Сільпо забороняють масовий збір асортименту та цін);
- нічого не пише в акаунт.
Ліміт рахується на користувача, тож після запуску кілька хвилин можливі відмови й у застосунку Сільпо.

    SILPO_MCP_URL=https://mcp.silpo.ua/mcp uv run python check_rate_limit.py
"""
import asyncio
import os
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from silpo_auth import make_auth

URL = os.environ.get("SILPO_MCP_URL", "https://mcp.silpo.ua/mcp")
WAVES = (1, 5, 10, 20, 40)
PAUSE = 3  # секунд між хвилями


def flatten(exc: BaseException) -> list[BaseException]:
    """ExceptionGroup з anyio розгортаємо в плоский список."""
    if isinstance(exc, BaseExceptionGroup):
        return [e for sub in exc.exceptions for e in flatten(sub)]
    return [exc]


async def one_call(session: ClientSession, n: int) -> tuple[int, float, str | None]:
    """Повертає (номер, секунди, опис помилки або None)."""
    started = time.monotonic()
    try:
        result = await session.call_tool("silpo_get_my_food_restrictions", {})
        text = result.content[0].text if result.content else ""
        if result.isError or not text.lstrip().startswith("{"):
            return n, time.monotonic() - started, f"tool-відповідь isError={result.isError}: {text[:300]!r}"
        return n, time.monotonic() - started, None
    except Exception as e:  # noqa: BLE001 - нам потрібен будь-який вигляд помилки
        return n, time.monotonic() - started, f"виняток {type(e).__name__}: {str(e)[:300]}"


async def run() -> None:
    sent = 0
    async with streamablehttp_client(URL, auth=make_auth(URL)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for wave in WAVES:
                results = await asyncio.gather(*(one_call(session, sent + i) for i in range(wave)))
                sent += wave
                failed = [r for r in results if r[2]]
                slowest = max(r[1] for r in results)
                print(f"хвиля {wave:>2}: ок {wave - len(failed)}/{wave}, найповільніший {slowest:.2f} с")
                if failed:
                    print(f"\nПЕРША ПОМИЛКА після {sent} запитів у цілому:")
                    for n, secs, err in failed[:3]:
                        print(f"  запит #{n} ({secs:.2f} с): {err}")
                    print("\nСкиньте цей вивід розробнику клієнта, щоб налаштувати розпізнавання ліміту.")
                    return
                await asyncio.sleep(PAUSE)
    print(f"\nУсі {sent} запитів пройшли без помилок: ліміт значно вищий за те, що потрібно сервісу.")


try:
    asyncio.run(run())
except BaseException as e:  # помилка могла прийти при закритті транспорту, а не з call_tool
    if isinstance(e, (KeyboardInterrupt, SystemExit)):
        raise
    print("\nНЕОЧІКУВАНИЙ ВИНЯТОК (можливо, це і є реакція на ліміт):")
    for sub in flatten(e):
        print(f"  {type(sub).__name__}: {str(sub)[:400]}")
