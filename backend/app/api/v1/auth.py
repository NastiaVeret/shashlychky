from datetime import timedelta

from fastapi import APIRouter, Response, status

from app.api.deps import SESSION_COOKIE, SessionToken, SettingsDep, clear_session_cookie
from app.core.config import Settings
from app.db.session import DbSession
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead
from app.services import auth as service

router = APIRouter(prefix="/auth", tags=["auth"])


async def start_session(
    response: Response, db: DbSession, settings: Settings, user: User
) -> UserRead:
    ttl = timedelta(days=settings.session_ttl_days)
    token = await service.create_session(db, user, ttl)
    # Commit before the response leaves, so the cookie never points at an unsaved session.
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    # Firebase Hosting has a CDN in front of Cloud Run; never let it cache a response that sets a
    # session.
    response.headers["Cache-Control"] = "no-store"
    return UserRead.model_validate(user)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest, response: Response, db: DbSession, settings: SettingsDep
) -> UserRead:
    """Create an account and log in right away."""
    user = await service.register(db, req.email, req.password)
    return await start_session(response, db, settings, user)


@router.post("/login", response_model=UserRead)
async def login(
    req: LoginRequest, response: Response, db: DbSession, settings: SettingsDep
) -> UserRead:
    user = await service.authenticate(db, settings, req.email, req.password)
    return await start_session(response, db, settings, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, db: DbSession, settings: SettingsDep, token: SessionToken = None
) -> None:
    """Revoke the current session. Succeeds without a session too, so the UI can always call it."""
    if token:
        await service.delete_session(db, token)
        await db.commit()
    clear_session_cookie(response, settings)
