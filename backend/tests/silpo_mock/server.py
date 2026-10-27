"""Mock MCP-сервер Сільпо.

Імітує підмножину tools реального сервера https://mcp.silpo.ua/mcp
(ті самі назви, параметри та форма відповідей, знята з реальних викликів),
але віддає дані з fixtures/ і тримає кошик у пам'яті. Без логіну й OTP.

Запуск: uv run python -m tests.silpo_mock.server   ->  http://127.0.0.1:8010/mcp
"""

import json
import uuid
from pathlib import Path

from mcp.server.fastmcp import FastMCP

FIXTURES = Path(__file__).parent / "fixtures"
PRODUCTS = json.loads((FIXTURES / "products.json").read_text(encoding="utf-8"))
DETAILS = json.loads((FIXTURES / "product_details.json").read_text(encoding="utf-8"))

BRANCH_ID = "1ee56cb2-afaa-60e6-8ee5-e17d00bb2c74"
COMPANY_ID = "1ec88c5d-a050-669c-8467-570a157f3e31"
CART_ID = "00000000-0000-4000-8000-00000000c0a7"  # synthetic
SLOT = {"start": "2026-10-23T13:30:00+00:00", "end": "2026-10-23T15:00:00+00:00"}

MIN_ORDER_COST = 799  # як у реальному Сільпо для доставки
STALE_SLOT = {"start": "2026-10-20T13:30:00+00:00", "end": "2026-10-20T15:00:00+00:00"}

mcp = FastMCP("silpo-mock", host="127.0.0.1", port=8010)

# стан кошика: id рядка -> {productId, quantity}
_cart: dict[str, dict] = {}
_restrictions: list[str] = []
_cart_slot: dict = dict(STALE_SLOT)  # як у реальному акаунті: слот кошика протух


def _reset() -> None:
    """Для тестів: порожній кошик і протухлий слот."""
    _cart.clear()
    _cart_slot.clear()
    _cart_slot.update(STALE_SLOT)


def _by_id(product_id: str) -> dict | None:
    return next((p for p in PRODUCTS if p["id"] == product_id), None)


def _search(query: str, limit: int) -> dict:
    def norm(t: str) -> str:
        return t.lower().replace(",", ".")

    words = norm(query).split()
    found = [p for p in PRODUCTS if all(w in norm(p["name"]) for w in words)]
    return {"query": query, "totalFound": len(found), "products": found[:limit]}


@mcp.tool()
def silpo_get_my_shopping_cart() -> dict:
    """Ідентифікатор активного кошика користувача. Починати завжди звідси."""
    return {"success": True, "shoppingCartId": CART_ID, "exists": True}


@mcp.tool()
def silpo_get_shopping_cart_by_id(shoppingCartId: str) -> dict:
    """Кошик: товари, доставка, слот, підсумки та validations[]."""
    lines, total, validations = [], 0.0, []
    if _cart_slot != SLOT:
        validations.append(
            {"level": "error", "type": "timeslot", "message": "timeslot.not_found", "context": []}
        )
    for line_id, item in list(_cart.items()):
        p = _by_id(item["productId"])
        lines.append(
            {
                "id": line_id,
                "productId": p["id"],
                "companyId": COMPANY_ID,
                "name": p["name"],
                "quantity": item["quantity"],
                "price": p["price"],
            }
        )
        total += p["price"] * item["quantity"]
        if item["quantity"] > p["stock"]:
            validations.append(
                {
                    "level": "error",
                    "type": "product",
                    "message": "product.offer.stock.max",
                    "context": {"stock": p["stock"]},
                }
            )
    if 0 < total < MIN_ORDER_COST:
        validations.append(
            {
                "level": "error",
                "type": "order",
                "message": "order.cost.min",
                "context": {"orderCostMin": MIN_ORDER_COST},
            }
        )
    links = {}
    if (
        total >= MIN_ORDER_COST and _cart_slot == SLOT
    ):  # як у реалі: посилання лише для кошика, який можна оформити
        links = {
            "checkoutWebLink": "https://silpo.ua/checkout-new",
            "checkoutMobileLink": "https://link.silpo.ua/mock",
        }
    return {
        "success": True,
        **links,
        "cart": {
            "id": shoppingCartId,
            "deliveryType": "DeliveryHome",
            "timeslot": _cart_slot,
            "address": {
                "addressType": "flat",
                "latitude": "49.82",
                "longitude": "24.01",
                "city": "Львів",
            },
            "shipments": [
                {
                    "id": shoppingCartId,
                    "companyId": COMPANY_ID,
                    "branchId": BRANCH_ID,
                    "products": lines,
                }
            ],
            "calculation": {
                "total": round(total, 2),
                "totalAfterDiscounts": round(total, 2),
                "productsTotal": round(total, 2),
                "validations": validations,
            },
        },
        "loyalty": {
            "bonusAvailable": 0,
            "bonusTotal": 0,
            "bonusRequested": None,
            "isEnabled": True,
        },
    }


@mcp.tool()
def silpo_update_shopping_cart(
    shoppingCartId: str, deliveryType: str, timeslot: dict, address: dict, shipments: list[dict]
) -> dict:
    """Параметри доставки кошика. У mock міняється лише слот."""
    _cart_slot.clear()
    _cart_slot.update(timeslot)
    return {"success": True}


@mcp.tool()
def silpo_get_time_slots(
    branchId: str,
    deliveryTypes: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> dict:
    """Доступні слоти доставки (час UTC)."""
    slot = {
        **SLOT,
        "available": True,
        "deliveryType": "DeliveryHome",
        "deliveryCost": 99,
        "minOrderCost": 799,
    }
    return {
        "success": True,
        "summary": "Found 1 time slots (1 available)",
        "slots": [slot],
        "meta": {"total": 1, "mayHaveMore": False},
    }


@mcp.tool()
def silpo_find_products_batch(
    branchId: str,
    deliveryType: str,
    timeslotStart: str,
    timeslotEnd: str,
    products: list[str],
    limit: int = 30,
) -> dict:
    """Пошук до 30 товарів за назвами одним викликом."""
    queries = [_search(q, limit) for q in products if q.strip()]
    return {
        "success": True,
        "summary": f"Found {sum(len(q['products']) for q in queries)} products across {len(queries)} search queries",
        "queries": queries,
        "meta": {
            "totalQueries": len(queries),
            "totalProducts": sum(len(q["products"]) for q in queries),
            "droppedCount": len(products) - len(queries),
        },
    }


@mcp.tool()
def silpo_get_product_details(
    branchId: str, slug: str, deliveryType: str, timeslotStart: str, timeslotEnd: str
) -> dict:
    """Картка товару: калорійність, БЖВ. Складу й алергенів у реальній відповіді немає."""
    p = next((p for p in PRODUCTS if p["slug"] == slug), None)
    if not p:
        return {"success": False, "error": "product not found"}
    extra = DETAILS.get(p["id"], {"hasOfferAtBranch": True, "attributes": {}})
    return {"success": True, "product": {**p, **extra}}


@mcp.tool()
def silpo_get_similar_products(
    branchId: str,
    slug: str,
    deliveryType: str,
    timeslotStart: str,
    timeslotEnd: str,
    limit: int = 10,
    offset: int = 0,
) -> dict:
    """Схожі товари (альтернативи). У mock: товари з тим самим першим словом назви."""
    src = next((p for p in PRODUCTS if p["slug"] == slug), None)
    if not src:
        return {"success": False, "error": "product not found"}
    first = src["name"].split()[0].lower()
    similar = [p for p in PRODUCTS if p["id"] != src["id"] and p["name"].lower().startswith(first)]
    return {
        "success": True,
        "products": similar[offset : offset + limit],
        "meta": {"total": len(similar)},
    }


@mcp.tool()
def silpo_get_my_food_restrictions() -> dict:
    """Харчові обмеження користувача (у mock порожні, змінюються в тестах)."""
    return {
        "success": True,
        "summary": "No food restrictions set" if not _restrictions else "Restrictions set",
        "restrictions": _restrictions,
    }


@mcp.tool()
def silpo_add_cart_products(shoppingCartId: str, products: list[dict]) -> dict:
    """Додати НОВІ товари: [{productId, companyId, branchId, quantity}]. Як і в реалі,
    неіснуючий productId мовчки ігнорується, тому результат треба перевіряти читанням кошика."""
    for item in products:
        if _by_id(item["productId"]) is None:
            continue
        if any(l["productId"] == item["productId"] for l in _cart.values()):
            return {
                "success": False,
                "error": "product already in cart, use silpo_update_cart_products",
            }
        _cart[str(uuid.uuid4())] = {"productId": item["productId"], "quantity": item["quantity"]}
    return {"success": True}


@mcp.tool()
def silpo_update_cart_products(shoppingCartId: str, products: list[dict]) -> dict:
    """Змінити кількість (АБСОЛЮТНА, не приріст): [{id (рядок кошика), quantity}]."""
    for item in products:
        if item["id"] in _cart:
            _cart[item["id"]]["quantity"] = item["quantity"]
    return {"success": True}


@mcp.tool()
def silpo_remove_cart_products(shoppingCartId: str, products: list[dict]) -> dict:
    """Видалити рядки кошика: [{id}]."""
    for item in products:
        _cart.pop(item["id"], None)
    return {"success": True}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
