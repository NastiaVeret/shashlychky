"""TokenStorage backed by the database, for the web service.

Mirrors FileTokenStorage: tokens + client registration + `saved_at`, so the provider can tell
when a loaded token expires and refresh it instead of asking for a login. By default it uses the
shared service row (`silpo_tokens`, id=1); `for_user` points it at a user's `silpo_connections`.
"""

import time
import uuid

from mcp.client.auth import TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.silpo_connection import SilpoConnection
from app.models.silpo_token import SilpoToken

SHARED_ROW_ID = 1

type TokenRow = SilpoToken | SilpoConnection


class DbTokenStorage(TokenStorage):
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        row_id: int | uuid.UUID = SHARED_ROW_ID,
    ):
        self._sessionmaker = sessionmaker
        self._row_id = row_id
        # A user id selects the user's connection, an int the shared service row.
        self._model: type[TokenRow] = (
            SilpoConnection if isinstance(row_id, uuid.UUID) else SilpoToken
        )

    @classmethod
    def for_user(
        cls, sessionmaker: async_sessionmaker[AsyncSession], user_id: uuid.UUID
    ) -> "DbTokenStorage":
        return cls(sessionmaker, user_id)

    async def _get(self, session: AsyncSession) -> TokenRow | None:
        return await session.get(self._model, self._row_id)

    async def _row(self, session: AsyncSession) -> TokenRow:
        row = await self._get(session)
        if row is None:
            row = (
                SilpoConnection(user_id=self._row_id)
                if isinstance(self._row_id, uuid.UUID)
                else SilpoToken(id=self._row_id)
            )
            session.add(row)
        return row

    async def get_tokens(self) -> OAuthToken | None:
        async with self._sessionmaker() as session:
            row = await self._get(session)
            return OAuthToken(**row.tokens) if row and row.tokens else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        async with self._sessionmaker() as session:
            row = await self._row(session)
            row.tokens = tokens.model_dump(mode="json", exclude_none=True)
            row.saved_at = time.time()
            await session.commit()

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        async with self._sessionmaker() as session:
            row = await self._get(session)
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
            row = await self._get(session)
            if row is None or not row.tokens or row.saved_at is None:
                return None
            expires_in = row.tokens.get("expires_in")
            return (
                None
                if not isinstance(expires_in, int | float)
                else row.saved_at + float(expires_in)
            )
