# mcp-silpo

Підключення до MCP Сільпо для Cook 'n' Love: **mock-сервер** для розробки й тестів
та приклад клієнта. Реальний сервер: `https://mcp.silpo.ua/mcp`
([документація](https://ai-factory.silpo.ua/#developers)).

## Навіщо mock
Реальний сервер вимагає логін акаунтом Сільпо (телефон + OTP), віддає змінні дані й має ліміти (429).
Mock має ті самі назви tools, параметри та форму відповідей (знято з реальних викликів),
але віддає дані з `fixtures/` і не потребує авторизації. Для перемикання змінюється лише `SILPO_MCP_URL`.

## Запуск
```bash
uv sync
uv run python mock_server.py          # http://localhost:8000/mcp
SILPO_MCP_URL=http://localhost:8000/mcp uv run python client_example.py
uv run pytest
# або Docker
docker build -t mcp-silpo-mock . && docker run -p 8000:8000 mcp-silpo-mock
```

## Tools у mock
| Tool | Що робить |
|---|---|
| `silpo_get_my_shopping_cart` | id кошика (починати звідси) |
| `silpo_get_shopping_cart_by_id` | кошик, `branchId`, `deliveryType`, слот, підсумок, `validations[]` |
| `silpo_get_time_slots` | слоти доставки |
| `silpo_find_products_batch` | пошук до 30 товарів за назвами |
| `silpo_get_product_details` | картка товару (калорії, БЖВ) |
| `silpo_get_similar_products` | альтернативи |
| `silpo_get_my_food_restrictions` | харчові обмеження користувача |
| `silpo_add_cart_products` / `silpo_update_cart_products` / `silpo_remove_cart_products` | зміна кошика |

Реальний сервер має 40 tools; решта (доставка, лояльність, профіль тощо) у mock не реалізована.

## Важливо знати (з реальних викликів)
- Усі пошукові tools потребують контексту `branchId`, `deliveryType`, `timeslotStart/End`. Беруться з `silpo_get_shopping_cart_by_id`.
  Слот має бути актуальним (`silpo_get_time_slots`), інакше `stock` усіх товарів = 0.
- Для `weighted: true` товарів `step` і `quantity` у **кілограмах**; `displayRatio` лише для показу.
- `silpo_add_cart_products` повертає `success: true` навіть якщо товар не додано. Завжди перечитуй кошик.
- `silpo_update_cart_products` приймає **абсолютну** кількість і id **рядка кошика**, а не `productId`.
- **Складу й алергенів у картці товару немає.** Є лише калорії та БЖВ (`attributes`). Це обмежує F11.

## Авторизація реального сервера (OAuth 2.1 + PKCE)
Користувач входить через `auth.silpo.ua`, клієнт отримує токен і шле `Authorization: Bearer ...`.
Токени тримати тільки на бекенді. Для перевірки вручну:
`claude mcp add --transport http silpo https://mcp.silpo.ua/mcp`, потім `/mcp` в Claude Code.

## Умови використання Сільпо
Заборонено порівнювати ціни між мережами та масово збирати ціни чи асортимент.
Кешувати можна лише те, що користувач знайшов для свого кошика.
Fixtures — кілька товарів з реальних відповідей; не розширювати до копії каталогу.
