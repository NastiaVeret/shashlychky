import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.profiles import UserProfile

logger = logging.getLogger(__name__)


def get_profile(user: User) -> UserProfile:
    return UserProfile.model_validate(user.profile)


async def update_profile(db: AsyncSession, user: User, profile: UserProfile) -> UserProfile:
    """Replace the whole profile (PUT semantics)."""
    user.profile = profile.model_dump(mode="json")
    await db.flush()
    return profile


async def delete_user(db: AsyncSession, user: User) -> None:
    """Remove the account and everything that belongs to it (sessions cascade in the database)."""
    await db.delete(user)
    await db.flush()
    logger.info("user deleted id=%s", user.id)
