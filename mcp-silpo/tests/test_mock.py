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
