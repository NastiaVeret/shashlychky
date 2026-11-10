from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OAuthTokenColumns:
    """What `DbTokenStorage` reads and writes; shared by the service row and per-user rows."""

    tokens: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    client_info: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # Unix time the tokens were obtained; the SDK only knows `expires_in`, this makes it absolute.
    saved_at: Mapped[float | None] = mapped_column(Float)


class SilpoToken(OAuthTokenColumns, Base):
    """The service's own Silpo login: one shared row (id=1) for product search and nutrition,
    which are not user-specific. A user's own login is a `SilpoConnection`."""

    __tablename__ = "silpo_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
