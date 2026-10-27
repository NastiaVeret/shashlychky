from fastapi import APIRouter, Response

from app.api.deps import CurrentUser
from app.schemas.auth import UserRead

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserRead)
async def read_me(user: CurrentUser, response: Response) -> UserRead:
    """The logged-in user; 401 without a valid session."""
    response.headers["Cache-Control"] = "no-store"
    return UserRead.model_validate(user)
