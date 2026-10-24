"""ORM models. Import every model module here so Alembic autogenerate sees all tables."""

from app.db.base import Base

__all__ = ["Base"]
