"""Ручна перевірка вагового товару на РЕАЛЬНОМУ Сільпо (не автотест).

Додає у кошик куряче філе (weighted: true, кількість у кілограмах) в кількості одного кроку (`step`),
перевіряє суму в кошику, змінює на два кроки й прибирає. Якщо кошик не порожній на старті - нічого не робить.

    uv run python check_real_weighted.py
"""
import asyncio

from silpo_client import SilpoError, connect

URL = "https://mcp.silpo.ua/mcp"


async def main() -> None:
    async with connect(URL) as silpo:
        if await silpo._lines():
            print("Кошик не порожній, зупиняюсь, щоб нічого не зачепити")
            return
        products = (await silpo.find_products(["куряче філе"], limit=10))["куряче філе"]
        item = next((p for p in products if p["weighted"] and p["available"]), None)
        if item is None:
            print("Вагового товару в наявності не знайдено")
            return
        step = item["step"]
        print(f"товар: {item['name']} | ціна за кг: {item['price']} | step: {step} кг | displayRatio: {item['displayRatio']}")
        try:
            r = await silpo.add_products_verified([(item, step)])
            print("додавання:", "ok" if r.ok else r.errors, "| додано:", r.added)
            _, cart = await silpo.cart()
            line = cart["shipments"][0]["products"][0]
            expected = round(item["price"] * step, 2)
            print(f"у кошику quantity={line.get('quantity')} | сума товарів {cart['calculation']['productsTotal']} (очікуємо ~{expected})")
            print("set_quantity(2 кроки):", await silpo.set_quantity(item["id"], step * 2))
            _, cart = await silpo.cart()
            print(f"після зміни: сума {cart['calculation']['productsTotal']} (очікуємо ~{round(item['price'] * step * 2, 2)})")
        except SilpoError as e:
            print("помилка сервера:", e.text[:500])
        finally:
            left = await silpo.remove_products([item["id"]])
            print("після видалення лишилось:", left, "| рядків у кошику:", len(await silpo._lines()))


asyncio.run(main())
