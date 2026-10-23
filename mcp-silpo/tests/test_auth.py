"""Тести silpo_auth без реального Сільпо: сховище токенів і локальний сервер редіректу."""
import asyncio
import json
import stat
import sys
from pathlib import Path

import pytest
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

sys.path.insert(0, str(Path(__file__).parent.parent))
import silpo_auth  # noqa: E402
from silpo_auth import FileTokenStorage, make_auth, wait_for_callback  # noqa: E402


async def test_empty_storage_returns_none(tmp_path):
    st = FileTokenStorage(tmp_path / "t.json")
    assert await st.get_tokens() is None and await st.get_client_info() is None


async def test_tokens_roundtrip_and_file_is_private(tmp_path):
    st = FileTokenStorage(tmp_path / "t.json")
    await st.set_tokens(OAuthToken(access_token="A", token_type="Bearer", expires_in=3600, refresh_token="R"))
    got = await st.get_tokens()
    assert got.access_token == "A" and got.refresh_token == "R"
    assert stat.S_IMODE((tmp_path / "t.json").stat().st_mode) == 0o600


async def test_tokens_and_client_info_do_not_overwrite_each_other(tmp_path):
    st = FileTokenStorage(tmp_path / "t.json")
    await st.set_client_info(OAuthClientInformationFull(
        client_id="cid", redirect_uris=[silpo_auth.REDIRECT_URI], client_name="x"))
    await st.set_tokens(OAuthToken(access_token="A", token_type="Bearer"))
    assert (await st.get_client_info()).client_id == "cid"
    assert (await st.get_tokens()).access_token == "A"
    assert set(json.loads((tmp_path / "t.json").read_text())) == {"tokens", "client_info"}


async def test_new_storage_object_reads_what_the_previous_one_wrote(tmp_path):
    await FileTokenStorage(tmp_path / "t.json").set_tokens(OAuthToken(access_token="A", token_type="Bearer"))
    assert (await FileTokenStorage(tmp_path / "t.json").get_tokens()).access_token == "A"


async def _hit(path_and_query: str) -> str:
    for _ in range(50):  # сервер стартує асинхронно: пробуємо підключитись, поки не відповість
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", silpo_auth.REDIRECT_PORT)
            break
        except ConnectionRefusedError:
            await asyncio.sleep(0.05)
    else:
        raise AssertionError("callback-сервер не піднявся")
    writer.write(f"GET {path_and_query} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
    await writer.drain()
    reply = (await reader.read()).decode()
    writer.close()
    return reply


async def test_callback_returns_code_and_state():
    waiter = asyncio.create_task(wait_for_callback())
    reply = await _hit("/callback?code=abc123&state=xyz")
    assert await waiter == ("abc123", "xyz")
    assert "200 OK" in reply


async def test_callback_without_state_gives_none_state():
    waiter = asyncio.create_task(wait_for_callback())
    await _hit("/callback?code=only")
    assert await waiter == ("only", None)


async def test_callback_with_error_raises():
    waiter = asyncio.create_task(wait_for_callback())
    await _hit("/callback?error=access_denied")
    with pytest.raises(RuntimeError, match="access_denied"):
        await waiter


async def test_callback_port_is_released_after_use():
    waiter = asyncio.create_task(wait_for_callback())
    await _hit("/callback?code=1")
    await waiter
    await asyncio.sleep(0.1)
    with pytest.raises(ConnectionRefusedError):
        await asyncio.open_connection("127.0.0.1", silpo_auth.REDIRECT_PORT)


def test_make_auth_registers_expected_redirect_and_public_client(tmp_path):
    auth = make_auth("https://mcp.silpo.ua/mcp", FileTokenStorage(tmp_path / "t.json"))
    meta = auth.context.client_metadata
    assert [str(u) for u in meta.redirect_uris] == [silpo_auth.REDIRECT_URI]
    assert meta.token_endpoint_auth_method == "none"  # публічний клієнт: секрету немає, захист - PKCE
    assert "refresh_token" in meta.grant_types
