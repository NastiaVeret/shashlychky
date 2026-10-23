import json
import sys
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

sys.path.insert(0, str(Path(__file__).parent.parent))
import mock_server  # noqa: E402

CTX = {"branchId": mock_server.BRANCH_ID, "deliveryType": "DeliveryHome",
       "timeslotStart": mock_server.SLOT["start"], "timeslotEnd": mock_server.SLOT["end"]}


async def call(s, name, args=None):
    return json.loads((await s.call_tool(name, args or {})).content[0].text)


async def test_search_and_cart_flow():
    mock_server._cart.clear()
    async with create_connected_server_and_client_session(mock_server.mcp._mcp_server) as session:
        await _search_and_cart_flow(session)


async def test_unknown_product_silently_ignored():
    mock_server._cart.clear()
    async with create_connected_server_and_client_session(mock_server.mcp._mcp_server) as session:
        await _unknown_product_silently_ignored(session)


async def _search_and_cart_flow(session):
    found = await call(session, "silpo_find_products_batch", {**CTX, "products": ["яйця", ""]})
    assert found["meta"]["droppedCount"] == 1
    egg = found["queries"][0]["products"][0]
    await call(session, "silpo_add_cart_products", {"shoppingCartId": mock_server.CART_ID, "products": [
        {"productId": egg["id"], "companyId": egg["companyId"], "branchId": egg["branchId"], "quantity": 2}]})
    cart = (await call(session, "silpo_get_shopping_cart_by_id", {"shoppingCartId": mock_server.CART_ID}))["cart"]
    line = cart["shipments"][0]["products"][0]
    assert line["quantity"] == 2 and cart["calculation"]["total"] == round(egg["price"] * 2, 2)
    await call(session, "silpo_update_cart_products",
               {"shoppingCartId": mock_server.CART_ID, "products": [{"id": line["id"], "quantity": 999}]})
    cart = (await call(session, "silpo_get_shopping_cart_by_id", {"shoppingCartId": mock_server.CART_ID}))["cart"]
    assert cart["calculation"]["validations"][0]["message"] == "product.offer.stock.max"


async def _unknown_product_silently_ignored(session):
    await call(session, "silpo_add_cart_products", {"shoppingCartId": mock_server.CART_ID, "products": [
        {"productId": "nope", "companyId": "c", "branchId": "b", "quantity": 1}]})
    cart = (await call(session, "silpo_get_shopping_cart_by_id", {"shoppingCartId": mock_server.CART_ID}))["cart"]
    assert cart["shipments"][0]["products"] == []


async def test_client_detects_product_that_was_not_added():
    from silpo_client import SilpoClient
    mock_server._cart.clear()
    async with create_connected_server_and_client_session(mock_server.mcp._mcp_server) as session:
        silpo = SilpoClient(session)
        found = await silpo.find_products(["яйця"], limit=1)
        egg = found["яйця"][0]
        ghost = {**egg, "id": "00000000-0000-4000-8000-0000000000ff"}  # такого товару немає
        result = await silpo.add_products_verified([(egg, 1), (ghost, 1)])
        assert result.added == [egg["id"]]
        assert result.missing == [ghost["id"]]
        assert not result.ok


async def test_client_set_quantity_remove_and_similar():
    from silpo_client import SilpoClient
    mock_server._cart.clear()
    async with create_connected_server_and_client_session(mock_server.mcp._mcp_server) as session:
        silpo = SilpoClient(session)
        found = await silpo.find_products(["яйця курячі"], limit=1)
        egg = found["яйця курячі"][0]
        await silpo.add_products_verified([(egg, 1)])
        assert await silpo.set_quantity(egg["id"], 3)
        assert not await silpo.set_quantity("nope", 3)
        assert [p["name"] for p in await silpo.similar_products(egg)] == ["Яйця перепелині «Премія»®"]
        assert await silpo.remove_products([egg["id"]]) == []
        assert await silpo.food_restrictions() == []
