"""A user's own Silpo account: connect (OAuth in the browser), status, disconnect.

Separate from the shared service login in `silpo_tokens`, which product search and КБЖВ use.
The login spans two requests: `start` stores the pending state and PKCE verifier on the user's
row and returns the Silpo URL; `finish` (the callback) checks the state and stores the tokens.
Features that act on the user's behalf (cart) connect with `DbTokenStorage.for_user`.
"""

import hashlib
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import SilpoConnectError
from app.integrations.silpo.auth import SilpoAuthError
from app.integrations.silpo.web_auth import exchange_code, start_authorization
from app.models.silpo_connection import SilpoConnection
from app.schemas.silpo import SilpoConnectionRead

logger = logging.getLogger(__name__)

# How long the user has to log in on the Silpo page (phone + SMS code).
LOGIN_TTL = timedelta(minutes=15)
HTTP_TIMEOUT = 15.0

SILPO_FAILURES = (httpx.HTTPError, ValidationError, SilpoAuthError)


async def get_silpo_http() -> AsyncIterator[httpx.AsyncClient]:
    """FastAPI dependency; tests override it with a mock transport."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as http:
        yield http


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _server_url(settings: Settings) -> str:
    url = settings.silpo_mcp_url
    if not url or urlparse(url).hostname in ("localhost", "127.0.0.1"):
        # The mock has no OAuth, so there is nothing to connect to.
        raise SilpoConnectError("Підключення Сільпо не налаштоване на цьому сервері")
    return url


async def get_status(db: AsyncSession, user_id: uuid.UUID) -> SilpoConnectionRead:
    row = await db.get(SilpoConnection, user_id)
    if row is None or row.tokens is None:
        return SilpoConnectionRead(connected=False)
    return SilpoConnectionRead(connected=True, connected_at=row.connected_at)


async def start(
    db: AsyncSession, user_id: uuid.UUID, settings: Settings, http: httpx.AsyncClient
) -> str:
    """Begin a login and return the Silpo URL. An existing connection stays until it succeeds."""
    server_url = _server_url(settings)
    row = await db.get(SilpoConnection, user_id)
    if row is None:
        row = SilpoConnection(user_id=user_id)
        db.add(row)
    known = OAuthClientInformationFull(**row.client_info) if row.client_info else None
    try:
        pending = await start_authorization(server_url, settings.silpo_redirect_uri, http, known)
    except SILPO_FAILURES as exc:
        logger.warning("silpo login start failed: %s: %s", type(exc).__name__, exc)
        raise SilpoConnectError() from exc
    row.client_info = pending.client_info.model_dump(mode="json", exclude_none=True)
    row.state_hash = _hash(pending.state)
    row.code_verifier = pending.code_verifier
    row.started_at = datetime.now(UTC)
    return pending.authorize_url


async def finish(
    db: AsyncSession,
    user_id: uuid.UUID,
    code: str,
    state: str,
    settings: Settings,
    http: httpx.AsyncClient,
) -> None:
    """Complete the login started by `start` for this user. Raises SilpoConnectError."""
    server_url = _server_url(settings)
    row = await db.get(SilpoConnection, user_id)
    if (
        row is None
        or row.state_hash is None
        or row.code_verifier is None
        or row.client_info is None
        or row.started_at is None
        or row.state_hash != _hash(state)
        or datetime.now(UTC) - row.started_at > LOGIN_TTL
    ):
        raise SilpoConnectError("Вхід у Сільпо застарів. Спробуйте ще раз.")
    try:
        tokens = await exchange_code(
            server_url,
            settings.silpo_redirect_uri,
            OAuthClientInformationFull(**row.client_info),
            code,
            row.code_verifier,
            http,
        )
    except SILPO_FAILURES as exc:
        logger.warning("silpo code exchange failed: %s: %s", type(exc).__name__, exc)
        raise SilpoConnectError() from exc
    row.tokens = tokens.model_dump(mode="json", exclude_none=True)
    row.saved_at = time.time()
    row.connected_at = datetime.now(UTC)
    row.state_hash = row.code_verifier = row.started_at = None
    logger.info("silpo connected user_id=%s", user_id)


async def disconnect(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Forget the user's Silpo tokens. Idempotent."""
    row = await db.get(SilpoConnection, user_id)
    if row is not None:
        await db.delete(row)
        await db.flush()
        logger.info("silpo disconnected user_id=%s", user_id)
