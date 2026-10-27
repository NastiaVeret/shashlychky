import uuid

import pytest
from httpx import AsyncClient, Response

from app.api.deps import SESSION_COOKIE
from app.core.config import get_settings

PASSWORD = "correct-horse-battery"


def unique_email() -> str:
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


async def register(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post("/api/v1/auth/register", json={"email": email, "password": password})


async def login(client: AsyncClient, email: str, password: str = PASSWORD) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_register_returns_201_and_logs_in(client: AsyncClient, db_required: None) -> None:
    email = unique_email()

    response = await register(client, email)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == email
    assert "password" not in body and "password_hash" not in body
    set_cookie = response.headers["set-cookie"]
    assert f"{SESSION_COOKIE}=" in set_cookie
    assert "HttpOnly" in set_cookie and "Secure" in set_cookie and "SameSite=lax" in set_cookie
    assert response.headers["cache-control"] == "no-store"
    me = await client.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["id"] == body["id"]


async def test_register_normalizes_email(client: AsyncClient, db_required: None) -> None:
    email = unique_email()

    response = await register(client, f"  {email.upper()} ")

    assert response.status_code == 201
    assert response.json()["email"] == email


async def test_register_duplicate_email_returns_409(client: AsyncClient, db_required: None) -> None:
    email = unique_email()
    await register(client, email)

    response = await register(client, email.upper())

    assert response.status_code == 409
    assert response.json()["detail"] == "Користувач з таким email уже існує"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", PASSWORD),
        ("a@b", PASSWORD),
        ("user@example.com", "short"),
        ("user@example.com", "x" * 129),
    ],
)
async def test_register_with_invalid_input_returns_422(
    client: AsyncClient, email: str, password: str
) -> None:
    response = await register(client, email, password)

    assert response.status_code == 422


async def test_login_returns_200_and_session(client: AsyncClient, db_required: None) -> None:
    email = unique_email()
    await register(client, email)
    client.cookies.clear()

    response = await login(client, email.upper())

    assert response.status_code == 200, response.text
    assert response.json()["email"] == email
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_login_with_wrong_password_returns_401(
    client: AsyncClient, db_required: None
) -> None:
    email = unique_email()
    await register(client, email)
    client.cookies.clear()

    response = await login(client, email, "wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Невірний email або пароль"
    assert SESSION_COOKIE not in response.cookies


async def test_login_with_unknown_email_returns_same_401(
    client: AsyncClient, db_required: None
) -> None:
    response = await login(client, unique_email())

    assert response.status_code == 401
    assert response.json()["detail"] == "Невірний email або пароль"


async def test_login_locks_account_after_too_many_failures(
    client: AsyncClient, db_required: None
) -> None:
    email = unique_email()
    await register(client, email)
    client.cookies.clear()
    for _ in range(get_settings().login_max_attempts):
        assert (await login(client, email, "wrong-password")).status_code == 401

    response = await login(client, email)  # the right password no longer helps

    assert response.status_code == 429
    assert "Забагато" in response.json()["detail"]


async def test_successful_login_resets_failure_counter(
    client: AsyncClient, db_required: None
) -> None:
    email = unique_email()
    await register(client, email)
    for _ in range(get_settings().login_max_attempts - 1):
        await login(client, email, "wrong-password")
    assert (await login(client, email)).status_code == 200

    response = await login(client, email, "wrong-password")

    assert response.status_code == 401  # counter started over, so this is not a lockout


async def test_logout_revokes_session(client: AsyncClient, db_required: None) -> None:
    token = (await register(client, unique_email())).cookies[SESSION_COOKIE]

    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401
    # the old token is dead on the server, not just forgotten by the browser
    reused = await client.get("/api/v1/me", headers={"Cookie": f"{SESSION_COOKIE}={token}"})
    assert reused.status_code == 401


async def test_logout_without_session_returns_204(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204


async def test_me_without_session_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Потрібно увійти"


async def test_me_with_unknown_token_returns_401(client: AsyncClient, db_required: None) -> None:
    response = await client.get("/api/v1/me", headers={"Cookie": f"{SESSION_COOKIE}=forged"})

    assert response.status_code == 401
