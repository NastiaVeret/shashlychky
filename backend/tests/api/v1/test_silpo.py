import uuid
from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.integrations.silpo.db_storage import DbTokenStorage
from app.main import app
from app.services.silpo_connections import get_silpo_http
from tests.api.v1.test_auth import register, unique_email
from tests.integrations.test_silpo_web_auth import SERVER, FakeSilpo, challenge_of

CONNECTION = "/api/v1/silpo/connection"
CALLBACK = "/api/v1/silpo/callback"


@pytest.fixture
def silpo() -> Iterator[FakeSilpo]:
    fake = FakeSilpo()
    settings = get_settings().model_copy(
        update={"silpo_mcp_url": SERVER, "cors_origins": "https://test"}
    )

    async def fake_http():  # type: ignore[no-untyped-def]
        async with fake.client() as http:
            yield http

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_silpo_http] = fake_http
    yield fake
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_silpo_http, None)


@pytest.fixture
async def logged_in(client: AsyncClient, db_required: None) -> str:
    response = await register(client, unique_email())
    assert response.status_code == 201
    return str(response.json()["id"])


async def start(client: AsyncClient) -> dict[str, str]:
    response = await client.post(CONNECTION)
    assert response.status_code == 200, response.text
    return {k: v[0] for k, v in parse_qs(urlparse(response.json()["authorize_url"]).query).items()}


async def callback(client: AsyncClient, **params: str) -> str:
    response = await client.get(CALLBACK, params=params)
    assert response.status_code == 302
    return response.headers["location"]


async def test_new_user_is_not_connected(client: AsyncClient, logged_in: str) -> None:
    response = await client.get(CONNECTION)

    assert response.status_code == 200
    assert response.json() == {"connected": False, "connected_at": None}


async def test_connection_requires_login(client: AsyncClient) -> None:
    assert (await client.get(CONNECTION)).status_code == 401
    assert (await client.post(CONNECTION)).status_code == 401


async def test_connect_flow_stores_tokens_for_the_user(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    params = await start(client)

    assert params["redirect_uri"] == "https://test/api/v1/silpo/callback"
    location = await callback(client, code="the-code", state=params["state"])

    assert location == "/profile?silpo=connected"
    body = (await client.get(CONNECTION)).json()
    assert body["connected"] is True and body["connected_at"]
    (sent,) = silpo.token_requests
    assert challenge_of(sent["code_verifier"][0]) == params["code_challenge"]
    storage = DbTokenStorage.for_user(get_sessionmaker(), uuid.UUID(logged_in))
    tokens = await storage.get_tokens()
    assert tokens is not None and tokens.refresh_token == "R"


async def test_callback_with_wrong_state_does_not_connect(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    await start(client)

    location = await callback(client, code="the-code", state="forged")

    assert location == "/profile?silpo=error"
    assert silpo.token_requests == []
    assert (await client.get(CONNECTION)).json()["connected"] is False


async def test_callback_state_is_single_use(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    params = await start(client)
    await callback(client, code="c", state=params["state"])

    assert await callback(client, code="c", state=params["state"]) == "/profile?silpo=error"


async def test_callback_when_user_declines(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    params = await start(client)

    location = await callback(client, error="access_denied", state=params["state"])

    assert location == "/profile?silpo=denied"


async def test_callback_without_session_does_not_connect(client: AsyncClient) -> None:
    assert await callback(client, code="c", state="s") == "/profile?silpo=error"


async def test_rejected_code_redirects_with_error(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    silpo.fail_token = True
    params = await start(client)

    assert await callback(client, code="c", state=params["state"]) == "/profile?silpo=error"
    assert (await client.get(CONNECTION)).json()["connected"] is False


async def test_reconnect_reuses_client_registration(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    await start(client)
    await start(client)

    assert silpo.registrations == 1


async def test_disconnect_forgets_tokens(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    params = await start(client)
    await callback(client, code="c", state=params["state"])

    response = await client.delete(CONNECTION)

    assert response.status_code == 204
    assert (await client.get(CONNECTION)).json()["connected"] is False
    assert (await client.delete(CONNECTION)).status_code == 204


async def test_connect_when_silpo_fails_returns_503(
    client: AsyncClient, logged_in: str, silpo: FakeSilpo
) -> None:
    silpo.fail_registration = True

    response = await client.post(CONNECTION)

    assert response.status_code == 503
    assert response.json()["detail"] == "Не вдалося підключити Сільпо. Спробуйте ще раз."


async def test_connect_without_silpo_configured_returns_503(
    client: AsyncClient, logged_in: str
) -> None:
    settings = get_settings().model_copy(update={"silpo_mcp_url": None})
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = await client.post(CONNECTION)
    finally:
        app.dependency_overrides.pop(get_settings, None)

    assert response.status_code == 503
