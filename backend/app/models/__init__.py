"""ORM models. Import every model module here so Alembic autogenerate sees all tables."""

from app.db.base import Base
from app.models.recipe import Recipe

__all__ = ["Base", "Recipe"]
