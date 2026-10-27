"""Email + password accounts with server-side sessions.

Passwords are hashed with Argon2id off the event loop. A session is a random token in an
httpOnly cookie; the database keeps only its SHA-256, so a leaked table cannot be replayed.
"""

import asyncio
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, InvalidCredentialsError, TooManyLoginAttemptsError
from app.models.auth_session import AuthSession
from app.models.user import User

logger = logging.getLogger(__name__)

# OWASP minimum for Argon2id (19 MiB, t=2, p=1). The library default (64 MiB, p=4) lets a burst
# of logins exhaust a 512 MiB Cloud Run instance.
_hasher = PasswordHasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
# Verified against when the email is unknown, so response time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash("timing-equaliser")


async def hash_password(password: str) -> str:
    # Argon2 is deliberately slow and CPU-bound; keep it off the event loop.
    return await asyncio.to_thread(_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    try:
        return await asyncio.to_thread(_hasher.verify, password_hash, password)
    except VerificationError:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register(db: AsyncSession, email: str, password: str) -> User:
    user = User(email=email, password_hash=await hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Користувач з таким email уже існує") from exc
    await db.refresh(user)
    logger.info("user registered id=%s", user.id)
    return user


async def authenticate(db: AsyncSession, settings: Settings, email: str, password: str) -> User:
    """Return the user for valid credentials; count failures and lock the account after too many."""
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user is None:
        await verify_password(_DUMMY_HASH, password)
        raise InvalidCredentialsError()

    now = datetime.now(UTC)
    if user.locked_until is not None and user.locked_until > now:
        raise TooManyLoginAttemptsError()

    if not await verify_password(user.password_hash, password):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.login_max_attempts:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_attempts = 0
            logger.warning("login locked user=%s", user.id)
        # The error below makes get_db roll back; the failure counter must survive it.
        await db.commit()
        raise InvalidCredentialsError()

    user.failed_login_attempts = 0
    user.locked_until = None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = await hash_password(password)
    return user


async def create_session(db: AsyncSession, user: User, ttl: timedelta) -> str:
    """Store a new session and return the raw token for the cookie."""
    now = datetime.now(UTC)
    # Housekeeping: a user's expired sessions are dropped whenever they log in again.
    await db.execute(
        delete(AuthSession).where(AuthSession.user_id == user.id, AuthSession.expires_at <= now)
    )
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=_hash_token(token), expires_at=now + ttl))
    await db.flush()
    return token


async def get_user_by_token(db: AsyncSession, token: str) -> User | None:
    stmt = (
        select(User)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.token_hash == _hash_token(token), AuthSession.expires_at > func.now())
    )
    return await db.scalar(stmt)


async def delete_session(db: AsyncSession, token: str) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.token_hash == _hash_token(token)))
