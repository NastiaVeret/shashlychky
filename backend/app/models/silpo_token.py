from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SilpoToken(Base):
    """OAuth tokens for the Silpo MCP server. One shared row (id=1) for now: product search and
    nutrition are not user-specific. Per-user rows come with the cart feature."""

    __tablename__ = "silpo_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tokens: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    client_info: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # Unix time the tokens were obtained; the SDK only knows `expires_in`, this makes it absolute.
    saved_at: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
