"""Тести SilpoClient без мережі: підроблена сесія з наперед заданими відповідями."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import silpo_client  # noqa: E402
from silpo_client import SilpoClient, SilpoError  # noqa: E402

BRANCH, COMPANY = "11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222"
ADDRESS = {"addressType": "flat", "latitude": "49.8", "longitude": "24.0", "city": "Львів", "entrance": None}
STALE = {"start": "2026-10-20T13:30:00+00:00", "end": "2026-10-20T15:00:00+00:00"}
FRESH = {"start": "2026-10-23T10:30:00+00:00", "end": "2026-10-23T12:00:00+00:00"}


class Result:
    def __init__(self, payload, is_error=False):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        self.content = [type("C", (), {"text": text})()]
        self.isError = is_error


class Session:
    """handlers: назва tool'а -> dict | callable(args) | список відповідей по черзі."""

    def __init__(self, **handlers):
        self.handlers, self.calls = handlers, []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        h = self.handlers[name]
        if isinstance(h, list):
            h = h.pop(0) if len(h) > 1 else h[0]
        out = h(args) if callable(h) else h
        if isinstance(out, BaseException):
            raise out
        return out if isinstance(out, Result) else Result(out)

    def names(self):
        return [n for n, _ in self.calls]

    def args_of(self, name):
        return [a for n, a in self.calls if n == name]


def cart_payload(slot, delivery_type="DeliveryHome", validations=(), products=()):
    return {"success": True, "cart": {
        "id": "cart-1", "deliveryType": delivery_type, "timeslot": slot, "address": ADDRESS,
        "shipments": [{"companyId": COMPANY, "branchId": BRANCH, "products": list(products)}],
        "calculation": {"validations": list(validations)}}}


def slots_payload(*slots, available=True):
    return {"success": True, "slots": [{**s, "available": available} for s in slots]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    sleeps = []

    async def fake(d):
        sleeps.append(d)

    monkeypatch.setattr(silpo_client.asyncio, "sleep", fake)
    return sleeps


def session_with(cart, slots, **extra):
    return Session(silpo_get_my_shopping_cart={"success": True, "shoppingCartId": "cart-1", "exists": True},
                   silpo_get_shopping_cart_by_id=cart, silpo_get_time_slots=slots,
                   silpo_update_shopping_cart={"success": True}, **extra)


# ---------- ensure_valid_slot ----------

async def test_valid_slot_is_left_alone():
    s = session_with(cart_payload(FRESH), slots_payload(FRESH, {"start": "2026-10-23T12:00:00+00:00", "end": "2026-10-23T13:30:00+00:00"}))
    assert await SilpoClient(s).ensure_valid_slot() is True
    assert "silpo_update_shopping_cart" not in s.names()


async def test_slot_is_compared_by_instant_not_by_string():
    zulu = {"start": "2026-10-23T10:30:00Z", "end": "2026-10-23T12:00:00Z"}
    s = session_with(cart_payload(zulu), slots_payload(FRESH))
    assert await SilpoClient(s).ensure_valid_slot() is True
    assert "silpo_update_shopping_cart" not in s.names()


async def test_stale_slot_is_replaced_keeping_address_and_branch():
    carts = [cart_payload(STALE), cart_payload(STALE), cart_payload(FRESH)]
    s = session_with(carts, slots_payload(FRESH))
    assert await SilpoClient(s).ensure_valid_slot() is True
    (update,) = s.args_of("silpo_update_shopping_cart")
    assert update["timeslot"] == FRESH
    assert update["address"] == ADDRESS  # передано без змін, разом з null-полями
    assert update["shipments"] == [{"companyId": COMPANY, "branchId": BRANCH}]
    assert update["deliveryType"] == "DeliveryHome" and update["shoppingCartId"] == "cart-1"


async def test_picks_first_available_slot_skipping_unavailable():
    slots = {"success": True, "slots": [{**STALE, "available": False}, {**FRESH, "available": True}]}
    s = session_with([cart_payload(STALE), cart_payload(STALE), cart_payload(FRESH)], slots)
    await SilpoClient(s).ensure_valid_slot()
    assert s.args_of("silpo_update_shopping_cart")[0]["timeslot"] == FRESH


async def test_no_available_slots_raises():
    s = session_with(cart_payload(STALE), slots_payload(FRESH, available=False))
    with pytest.raises(RuntimeError, match="слот"):
        await SilpoClient(s).ensure_valid_slot()
    assert "silpo_update_shopping_cart" not in s.names()


async def test_returns_false_if_slot_error_remains():
    bad = cart_payload(STALE, validations=[{"level": "error", "type": "timeslot", "message": "timeslot.not_found"}])
    s = session_with(bad, slots_payload(FRESH))
    assert await SilpoClient(s).ensure_valid_slot() is False


async def test_express_delivery_asks_slots_as_home_delivery():
    s = session_with([cart_payload(STALE, "DeliveryExpressByPromise")] * 2 + [cart_payload(FRESH, "DeliveryExpressByPromise")],
                     slots_payload(FRESH))
    await SilpoClient(s).ensure_valid_slot()
    assert s.args_of("silpo_get_time_slots")[0]["deliveryTypes"] == ["DeliveryHome"]
    assert s.args_of("silpo_update_shopping_cart")[0]["deliveryType"] == "DeliveryExpressByPromise"


# ---------- search_context ----------

async def test_search_context_uses_cart_branch_and_first_available_slot_not_cart_slot():
    s = session_with(cart_payload(STALE), slots_payload(FRESH))
    ctx = await SilpoClient(s).search_context()
    assert ctx == {"branchId": BRANCH, "deliveryType": "DeliveryHome",
                   "timeslotStart": FRESH["start"], "timeslotEnd": FRESH["end"]}


async def test_search_context_without_slots_raises():
    s = session_with(cart_payload(STALE), slots_payload(FRESH, available=False))
    with pytest.raises(RuntimeError):
        await SilpoClient(s).search_context()


# ---------- call: помилки та ліміти ----------

async def test_tool_error_flagged_by_server_raises_with_text():
    s = Session(x=Result('{"success": false, "error": "boom"}', is_error=True))
    with pytest.raises(SilpoError) as e:
        await SilpoClient(s).call("x")
    assert "boom" in e.value.text and e.value.tool == "x"


async def test_empty_reply_raises_silpo_error():
    s = Session(x=Result(""))
    with pytest.raises(SilpoError):
        await SilpoClient(s).call("x")


async def test_rate_limit_as_exception_is_retried(no_sleep):
    s = Session(x=[RuntimeError("HTTP 429 Too Many Requests"), Result({"ok": 1})])
    assert await SilpoClient(s).call("x") == {"ok": 1}
    assert no_sleep == [1]


async def test_non_rate_limit_exception_propagates_immediately(no_sleep):
    s = Session(x=ConnectionError("connection reset"))
    with pytest.raises(ConnectionError):
        await SilpoClient(s).call("x")
    assert no_sleep == [] and len(s.calls) == 1


async def test_rate_limit_exception_gives_up_after_all_retries(no_sleep):
    s = Session(x=RuntimeError("429"))
    with pytest.raises(RuntimeError):
        await SilpoClient(s).call("x")
    assert no_sleep == [1, 2, 4] and len(s.calls) == 4


@pytest.mark.parametrize("text", ["Error 429", "Rate limit exceeded", "rate-limit", "Too Many Requests", "Забагато запитів"])
async def test_rate_limit_wordings_are_recognised(text, no_sleep):
    s = Session(x=[Result(text, is_error=True), Result({"ok": True})])
    assert await SilpoClient(s).call("x") == {"ok": True}
    assert no_sleep == [1]


@pytest.mark.parametrize("text", ["Product not found", "Invalid slug", "Unauthorized"])
async def test_ordinary_errors_are_not_retried(text, no_sleep):
    s = Session(x=Result(text, is_error=True))
    with pytest.raises(SilpoError):
        await SilpoClient(s).call("x")
    assert no_sleep == []


# ---------- add / quantity / remove на підробній сесії ----------

def line(product_id, qty, line_id="line-1"):
    return {"id": line_id, "productId": product_id, "quantity": qty}


PRODUCT = {"id": "p-1", "companyId": COMPANY, "branchId": BRANCH, "slug": "s", "name": "n", "price": 10}


async def test_add_sends_ids_from_search_result_and_verifies_presence():
    # читань кошика: 1 у ensure_valid_slot, 1 перед додаванням, 1 після нього (там товар уже є)
    carts = [cart_payload(FRESH)] * 2 + [cart_payload(FRESH, products=[line("p-1", 2)])]
    s = session_with(carts, slots_payload(FRESH), silpo_add_cart_products={"success": True})
    r = await SilpoClient(s).add_products_verified([(PRODUCT, 2)])
    assert s.args_of("silpo_add_cart_products")[0]["products"] == [
        {"productId": "p-1", "companyId": COMPANY, "branchId": BRANCH, "quantity": 2}]
    assert r.added == ["p-1"] and r.missing == [] and r.ok


async def test_add_reports_missing_when_server_silently_drops():
    s = session_with(cart_payload(FRESH), slots_payload(FRESH), silpo_add_cart_products={"success": True})
    r = await SilpoClient(s).add_products_verified([(PRODUCT, 1)])
    assert r.missing == ["p-1"] and not r.ok


async def test_add_separates_order_issues_from_add_errors():
    vals = [{"level": "error", "type": "order", "message": "order.cost.min", "context": {"orderCostMin": 799}},
            {"level": "error", "type": "product", "message": "product.offer.stock.max", "context": {"stock": 0}},
            {"level": "warning", "type": "x", "message": "ignored"}]
    s = session_with(cart_payload(FRESH, validations=vals, products=[line("p-1", 1)]), slots_payload(FRESH),
                     silpo_add_cart_products={"success": True})
    r = await SilpoClient(s).add_products_verified([(PRODUCT, 1)])
    assert [v["message"] for v in r.errors] == ["product.offer.stock.max"]
    assert [v["message"] for v in r.checkout_issues] == ["order.cost.min"]
    assert not r.ok


async def test_set_quantity_uses_line_id_and_reports_applied():
    # читань кошика: пошук рядка, id кошика для запису, перевірка після запису
    carts = [cart_payload(FRESH, products=[line("p-1", 1, "L9")])] * 2 + [cart_payload(FRESH, products=[line("p-1", 5, "L9")])]
    s = session_with(carts, slots_payload(FRESH), silpo_update_cart_products={"success": True})
    assert await SilpoClient(s).set_quantity("p-1", 5) is True
    assert s.args_of("silpo_update_cart_products")[0]["products"] == [{"id": "L9", "quantity": 5}]


async def test_set_quantity_false_if_server_ignored_it():
    s = session_with(cart_payload(FRESH, products=[line("p-1", 1)]), slots_payload(FRESH),
                     silpo_update_cart_products={"success": True})
    assert await SilpoClient(s).set_quantity("p-1", 5) is False


async def test_set_quantity_for_product_not_in_cart_does_not_call_server():
    s = session_with(cart_payload(FRESH), slots_payload(FRESH), silpo_update_cart_products={"success": True})
    assert await SilpoClient(s).set_quantity("p-1", 5) is False
    assert "silpo_update_cart_products" not in s.names()


async def test_remove_returns_leftovers_and_skips_unknown_ids():
    s = session_with(cart_payload(FRESH, products=[line("p-1", 1, "L1")]), slots_payload(FRESH),
                     silpo_remove_cart_products={"success": True})
    left = await SilpoClient(s).remove_products(["p-1", "nope"])
    assert left == ["p-1"]  # сервер "не видалив": у підробній сесії кошик не змінюється
    assert s.args_of("silpo_remove_cart_products")[0]["products"] == [{"id": "L1"}]


async def test_remove_with_nothing_to_remove_makes_no_write():
    s = session_with(cart_payload(FRESH), slots_payload(FRESH), silpo_remove_cart_products={"success": True})
    assert await SilpoClient(s).remove_products(["nope"]) == []
    assert "silpo_remove_cart_products" not in s.names()


# ---------- checkout_links ----------

async def test_checkout_links_read_from_top_level_and_slot_refreshed_first():
    payload = {**cart_payload(STALE), "checkoutWebLink": "W", "checkoutMobileLink": "M"}
    s = session_with([payload, payload, cart_payload(FRESH), payload], slots_payload(FRESH))
    links = await SilpoClient(s).checkout_links()
    assert links == {"web": "W", "mobile": "M"}
    assert s.names().index("silpo_update_shopping_cart") < len(s.names()) - 1


async def test_checkout_links_none_when_server_gives_none():
    s = session_with(cart_payload(FRESH), slots_payload(FRESH))
    assert await SilpoClient(s).checkout_links() == {"web": None, "mobile": None}


# ---------- food_restrictions / similar ----------

async def test_food_restrictions_returns_list_or_empty():
    assert await SilpoClient(Session(silpo_get_my_food_restrictions={"success": True, "restrictions": ["vegan"]})).food_restrictions() == ["vegan"]
    assert await SilpoClient(Session(silpo_get_my_food_restrictions={"success": False})).food_restrictions() == []


async def test_similar_products_passes_slug_and_context():
    s = session_with(cart_payload(STALE), slots_payload(FRESH),
                     silpo_get_similar_products={"success": True, "products": [{"id": "z"}]})
    out = await SilpoClient(s).similar_products(PRODUCT, limit=3)
    assert out == [{"id": "z"}]
    a = s.args_of("silpo_get_similar_products")[0]
    assert a["slug"] == "s" and a["limit"] == 3 and a["timeslotStart"] == FRESH["start"] and a["branchId"] == BRANCH


async def test_find_products_maps_query_to_products():
    s = session_with(cart_payload(STALE), slots_payload(FRESH), silpo_find_products_batch={
        "success": True, "queries": [{"query": "a", "products": [{"id": 1}]}, {"query": "b", "products": []}]})
    assert await SilpoClient(s).find_products(["a", "b"]) == {"a": [{"id": 1}], "b": []}
    assert s.args_of("silpo_find_products_batch")[0]["products"] == ["a", "b"]
