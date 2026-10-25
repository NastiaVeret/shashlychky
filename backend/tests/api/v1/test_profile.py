import pytest
from httpx import AsyncClient

from tests.api.v1.test_auth import PASSWORD, login, register, unique_email

FULL_PROFILE = {
    "allergies": ["арахіс"],
    "diets": ["vegetarian"],
    "disliked": ["цибуля"],
    "equipment": ["stovetop", "microwave"],
    "default_servings": 3,
    "pantry": ["рис", "олія"],
}


@pytest.fixture
async def logged_in(client: AsyncClient, db_required: None) -> str:
    email = unique_email()
    assert (await register(client, email)).status_code == 201
    return email


async def test_new_user_gets_default_profile(client: AsyncClient, logged_in: str) -> None:
    response = await client.get("/api/v1/me/profile")

    assert response.status_code == 200
    assert response.json() == {
        "allergies": [],
        "diets": [],
        "disliked": [],
        "equipment": [],
        "default_servings": 2,
        "pantry": [],
    }


async def test_put_profile_replaces_and_persists(client: AsyncClient, logged_in: str) -> None:
    response = await client.put("/api/v1/me/profile", json=FULL_PROFILE)

    assert response.status_code == 200, response.text
    assert response.json() == FULL_PROFILE
    assert (await client.get("/api/v1/me/profile")).json() == FULL_PROFILE


async def test_put_profile_normalizes_lists(client: AsyncClient, logged_in: str) -> None:
    response = await client.put(
        "/api/v1/me/profile",
        json={
            "allergies": [" Арахіс ", "арахіс", ""],
            "diets": ["vegan", "vegan"],
            "pantry": ["рис", "  рис  "],
        },
    )

    body = response.json()
    assert body["allergies"] == ["Арахіс"]
    assert body["diets"] == ["vegan"]
    assert body["pantry"] == ["рис"]


@pytest.mark.parametrize(
    "patch",
    [
        {"diets": ["carnivore"]},
        {"equipment": ["teleporter"]},
        {"default_servings": 0},
        {"pantry": [f"p{i}" for i in range(51)]},
    ],
)
async def test_put_invalid_profile_returns_422(
    client: AsyncClient, logged_in: str, patch: dict[str, object]
) -> None:
    response = await client.put("/api/v1/me/profile", json={**FULL_PROFILE, **patch})

    assert response.status_code == 422


async def test_profile_without_session_returns_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/me/profile")).status_code == 401
    assert (await client.put("/api/v1/me/profile", json=FULL_PROFILE)).status_code == 401


async def test_delete_me_removes_account(client: AsyncClient, logged_in: str) -> None:
    await client.put("/api/v1/me/profile", json=FULL_PROFILE)

    response = await client.delete("/api/v1/me")

    assert response.status_code == 204
    assert (await client.get("/api/v1/me")).status_code == 401
    assert (await login(client, logged_in, PASSWORD)).status_code == 401
    # the email is free again
    assert (await register(client, logged_in)).status_code == 201
    assert (await client.get("/api/v1/me/profile")).json()["allergies"] == []


async def test_delete_me_without_session_returns_401(client: AsyncClient) -> None:
    assert (await client.delete("/api/v1/me")).status_code == 401
