from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentUser, SettingsDep, clear_session_cookie
from app.api.v1.recipes import to_read
from app.db.session import DbSession
from app.schemas.auth import UserRead
from app.schemas.profiles import UserProfile
from app.schemas.recipes import RecipeRead
from app.services import profiles as service
from app.services import recipes as recipes_service

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserRead)
async def read_me(user: CurrentUser, response: Response) -> UserRead:
    """The logged-in user; 401 without a valid session."""
    response.headers["Cache-Control"] = "no-store"
    return UserRead.model_validate(user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    user: CurrentUser, response: Response, db: DbSession, settings: SettingsDep
) -> None:
    """Delete the account with its profile and sessions. Cannot be undone."""
    await service.delete_user(db, user)
    await db.commit()
    clear_session_cookie(response, settings)


@router.get("/recipes", response_model=list[RecipeRead])
async def list_my_recipes(
    user: CurrentUser,
    response: Response,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RecipeRead]:
    """The user's recipes, newest first."""
    response.headers["Cache-Control"] = "no-store"
    recipes = await recipes_service.list_user_recipes(db, user.id, limit, offset)
    return [to_read(r) for r in recipes]


@router.get("/profile", response_model=UserProfile)
async def read_profile(user: CurrentUser, response: Response) -> UserProfile:
    """Dietary profile and pantry; defaults for a user who never saved one."""
    response.headers["Cache-Control"] = "no-store"
    return service.get_profile(user)


@router.put("/profile", response_model=UserProfile)
async def update_profile(
    profile: UserProfile, user: CurrentUser, response: Response, db: DbSession
) -> UserProfile:
    """Replace the whole profile. Lists come back normalized (trimmed, de-duplicated)."""
    response.headers["Cache-Control"] = "no-store"
    return await service.update_profile(db, user, profile)
