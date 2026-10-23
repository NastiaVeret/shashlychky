"""Ручна перевірка запису в кошик РЕАЛЬНОГО Сільпо (не автотест).

Оновлює слот кошика (адреса й магазин лишаються), додає один товар, перевіряє, змінює кількість і в кінці прибирає його.
Якщо кошик не порожній на старті - нічого не робить. Запускати лише на тестовому акаунті
або з порожнім кошиком:

    SILPO_MCP_URL=https://mcp.silpo.ua/mcp uv run python check_real_cart.py
"""
import asyncio
import os

from silpo_client import SilpoError, connect

URL = os.environ.get("SILPO_MCP_URL", "https://mcp.silpo.ua/mcp")


async def main() -> None:
    async with connect(URL) as silpo:
        if await silpo._lines():
            print("Кошик не порожній, зупиняюсь, щоб нічого не зачепити")
            return
        _, cart = await silpo.cart()
        print("слот кошика до:", cart["timeslot"], "| адреса:", cart["address"]["locality"])
        print("ensure_valid_slot:", await silpo.ensure_valid_slot())
        _, cart = await silpo.cart()
        print("слот кошика після:", cart["timeslot"], "| адреса:", cart["address"]["locality"],
              "| помилки:", [v["message"] for v in cart["calculation"]["validations"] if v["level"] == "error"])
        item = (await silpo.find_products(["сир кисломолочний"], limit=1))["сир кисломолочний"][0]
        print("товар:", item["name"], item["price"], "stock", item["stock"], "weighted", item["weighted"])
        try:
            r = await silpo.add_products_verified([(item, 1)])
            print("додавання: додано", r.added, "не додано", r.missing, "помилки", r.errors, "ok", r.ok,
                  "| перешкоди оформленню:", [(v["message"], v["context"]) for v in r.checkout_issues])

            ghost = {**item, "id": "00000000-0000-4000-8000-0000000000ff"}
            try:
                r2 = await silpo.add_products_verified([(ghost, 1)])
                print("неіснуючий товар: не додано", r2.missing, "ok", r2.ok, "(очікуємо ok False)")
            except SilpoError as e:
                print("неіснуючий товар: сервер відповів помилкою:", e.text[:500])

            print("set_quantity(2):", await silpo.set_quantity(item["id"], 2))

            # Підняти суму вище мінімальної, щоб побачити, чи з'являться посилання на оформлення
            min_cost = next((v["context"]["orderCostMin"] for v in r.checkout_issues
                             if v["message"] == "order.cost.min"), None)
            if min_cost:
                qty = -(-min_cost // item["price"])  # ceil
                qty = min(int(qty), item["stock"])
                print(f"мінімальна сума {min_cost}, ставлю кількість {qty}:", await silpo.set_quantity(item["id"], qty))
            _, cart = await silpo.cart()
            print("сума:", cart["calculation"]["productsTotal"],
                  "validations:", [v["message"] for v in cart["calculation"]["validations"]])
            print("checkout_links:", await silpo.checkout_links())
        finally:
            left = await silpo.remove_products([item["id"]])
            print("після видалення лишилось:", left, "| рядків у кошику:", len(await silpo._lines()))


asyncio.run(main())
