"""Shared FastAPI dependencies: settings and the current user from the session cookie."""

from typing import Annotated

from fastapi import Cookie, Depends, Response

from app.core.config import Settings, get_settings
from app.core.errors import NotAuthenticatedError
from app.db.session import DbSession
from app.models.user import User
from app.services import auth as auth_service

# Not configurable on purpose: Firebase Hosting forwards only the cookie named `__session` to
# Cloud Run and strips every other one.
SESSION_COOKIE = "__session"

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


async def get_optional_user(db: DbSession, token: SessionToken = None) -> User | None:
    """The logged-in user, or None for anonymous requests (and expired or forged sessions)."""
    return await auth_service.get_user_by_token(db, token) if token else None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


async def get_current_user(user: OptionalUser) -> User:
    if user is None:
        raise NotAuthenticatedError()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=settings.session_cookie_secure, samesite="lax"
    )
