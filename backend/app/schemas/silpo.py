from datetime import datetime

from pydantic import BaseModel


class SilpoConnectionRead(BaseModel):
    """Whether the user's own Silpo account is connected. Tokens never leave the server."""

    connected: bool
    connected_at: datetime | None = None


class SilpoAuthorizeRead(BaseModel):
    """Where to send the browser to log in to Silpo; it comes back to /api/v1/silpo/callback."""

    authorize_url: str
