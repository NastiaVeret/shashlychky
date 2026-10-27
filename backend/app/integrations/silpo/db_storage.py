"""TokenStorage backed by the `silpo_tokens` table, for the web service.

Mirrors FileTokenStorage: tokens + client registration + `saved_at`, so the provider can tell
when a loaded token expires and refresh it instead of asking for a login.
"""

import time

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.silpo_token import SilpoToken

SHARED_ROW_ID = 1


class DbTokenStorage(TokenStorage):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession], row_id: int = SHARED_ROW_ID):
        self._sessionmaker = sessionmaker
        self._row_id = row_id

    async def _row(self, session: AsyncSession) -> SilpoToken:
        row = await session.get(SilpoToken, self._row_id)
        if row is None:
            row = SilpoToken(id=self._row_id)
            session.add(row)
        return row

    async def get_tokens(self) -> OAuthToken | None:
        async with self._sessionmaker() as session:
            row = await session.get(SilpoToken, self._row_id)
            return OAuthToken(**row.tokens) if row and row.tokens else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._sessionmaker() as session:
            row = await self._row(session)
            row.tokens = tokens.model_dump(mode="json", exclude_none=True)
            row.saved_at = time.time()
            await session.commit()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        async with self._sessionmaker() as session:
            row = await session.get(SilpoToken, self._row_id)
            return (
                OAuthClientInformationFull(**row.client_info) if row and row.client_info else None
            )

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        async with self._sessionmaker() as session:
            row = await self._row(session)
            row.client_info = client_info.model_dump(mode="json", exclude_none=True)
            await session.commit()

    async def expiry_time_async(self) -> float | None:
        async with self._sessionmaker() as session:
            row = await session.get(SilpoToken, self._row_id)
            if row is None or not row.tokens or row.saved_at is None:
                return None
            expires_in = row.tokens.get("expires_in")
            return (
                None
                if not isinstance(expires_in, int | float)
                else row.saved_at + float(expires_in)
            )
