from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, OptionalUser, SettingsDep
from app.core.errors import SilpoConnectError
from app.db.session import DbSession
from app.schemas.silpo import SilpoAuthorizeRead, SilpoConnectionRead
from app.services import silpo_connections as service

router = APIRouter(prefix="/silpo", tags=["silpo"])

SilpoHttp = Annotated[httpx.AsyncClient, Depends(service.get_silpo_http)]

# The profile page reads `?silpo=` and shows the outcome.
PROFILE_URL = "/profile"


@router.get("/connection", response_model=SilpoConnectionRead)
async def read_connection(
    user: CurrentUser, response: Response, db: DbSession
) -> SilpoConnectionRead:
    """Whether the user's Silpo account is connected."""
    response.headers["Cache-Control"] = "no-store"
    return await service.get_status(db, user.id)


@router.post("/connection", response_model=SilpoAuthorizeRead)
async def start_connection(
    user: CurrentUser, response: Response, db: DbSession, settings: SettingsDep, http: SilpoHttp
) -> SilpoAuthorizeRead:
    """Start the Silpo login; the frontend navigates to `authorize_url`. 503 if Silpo fails."""
    response.headers["Cache-Control"] = "no-store"
    url = await service.start(db, user.id, settings, http)
    return SilpoAuthorizeRead(authorize_url=url)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(user: CurrentUser, db: DbSession) -> None:
    """Disconnect the user's Silpo account."""
    await service.disconnect(db, user.id)


@router.get("/callback", response_class=RedirectResponse, include_in_schema=False)
async def silpo_callback(
    user: OptionalUser,
    db: DbSession,
    settings: SettingsDep,
    http: SilpoHttp,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Silpo sends the browser back here. Always redirects to the profile page with the outcome.

    The session cookie (SameSite=Lax survives this top-level redirect) must belong to the user
    who started the login, so nobody can attach their Silpo account to someone else's.
    """
    if error == "access_denied":
        outcome = "denied"
    elif user is None or code is None or state is None:
        outcome = "error"
    else:
        try:
            await service.finish(db, user.id, code, state, settings, http)
            outcome = "connected"
        except SilpoConnectError:
            outcome = "error"
    return RedirectResponse(
        f"{PROFILE_URL}?silpo={outcome}",
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store"},
    )
