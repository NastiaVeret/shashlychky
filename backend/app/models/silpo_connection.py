import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.silpo_token import OAuthTokenColumns


class SilpoConnection(OAuthTokenColumns, Base):
    """A user's own Silpo login, made from the profile page (OAuth in the browser).

    `tokens` is NULL until the first login completes. While a login is in progress the row
    holds its pending state; `client_info` (the dynamic client registration) is reused.
    """

    __tablename__ = "silpo_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Pending login: SHA-256 of the OAuth `state` and the PKCE verifier; cleared on success.
    state_hash: Mapped[str | None] = mapped_column(String(64))
    code_verifier: Mapped[str | None] = mapped_column(String(128))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
