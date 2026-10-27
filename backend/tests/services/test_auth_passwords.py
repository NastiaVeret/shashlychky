from app.services.auth import hash_password, verify_password


async def test_password_hash_is_argon2id_and_verifies() -> None:
    password_hash = await hash_password("correct-horse-battery")

    assert password_hash.startswith("$argon2id$")
    assert "correct-horse-battery" not in password_hash
    assert await verify_password(password_hash, "correct-horse-battery")
    assert not await verify_password(password_hash, "Correct-horse-battery")


async def test_same_password_gets_different_salts() -> None:
    assert await hash_password("same-password") != await hash_password("same-password")
