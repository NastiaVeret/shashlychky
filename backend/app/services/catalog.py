"""Silpo product data for recipes: one MCP session per request, one lookup budget.

КБЖВ, the allergen check and the shopping list all read the same product cards. Each of them
hands `run` a function that works with a `ProductCatalog`; this module opens the session,
enforces the deadline and turns every way Silpo can fail into one clean 503.
"""

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Protocol

import httpx
from fastapi import Depends
from mcp.shared.exceptions import McpError

from app.core.config import Settings, get_settings
from app.core.errors import ProductDataUnavailableError, SilpoAccountUnusableError
from app.db.session import get_sessionmaker
from app.integrations.silpo import (
    NoStoreSelectedError,
    SilpoError,
    SilpoNotConnectedError,
    connect,
)
from app.integrations.silpo.catalog import LOOKUP_DEADLINE_SECONDS, ProductCatalog
from app.integrations.silpo.db_storage import DbTokenStorage

logger = logging.getLogger(__name__)

# What counts as "Silpo did not answer" rather than a bug of ours.
_EXPECTED = (SilpoError, McpError, httpx.HTTPError, TimeoutError, OSError)
# Pause before each retry after an HTTP 429. SilpoClient already retries a 429 that arrives as a
# tool result or an MCP error, but a real HTTP 429 kills the whole transport (measured against a
# local server): the session is gone, so only opening a new one can retry it.
HTTP_429_RETRY_DELAYS = (1.0, 3.0)


def _is_http_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _first(group: BaseExceptionGroup[BaseException]) -> BaseException:
    """The first leaf exception of a (possibly nested) group."""
    inner = group.exceptions[0]
    return _first(inner) if isinstance(inner, BaseExceptionGroup) else inner


class CatalogProvider(Protocol):
    """Runs `work` against a fresh `ProductCatalog`.

    Raises `ProductDataUnavailableError` (or the subclass the provider was built with) when
    Silpo is not connected, does not answer or is too slow.
    """

    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T: ...


# The account itself is not usable, as opposed to Silpo not answering.
_ACCOUNT_PROBLEMS = (SilpoNotConnectedError, NoStoreSelectedError)


class ConnectedCatalogProvider:
    """Opens one MCP session per call. A localhost URL is the mock (no OAuth); the real server
    needs the stored login (see README, "Silpo login").

    With `user_id` the session is the user's own Silpo account, so prices and stock are those of
    their store. Only pass it for a user whose account is connected: an unconnected one would
    start an OAuth client registration on every request. When that account cannot be searched
    (login gone, no store picked) `run` raises `SilpoAccountUnusableError`.
    """

    def __init__(
        self,
        url: str,
        unavailable: type[ProductDataUnavailableError] = ProductDataUnavailableError,
        user_id: uuid.UUID | None = None,
    ) -> None:
        self._url = url
        self._unavailable = unavailable
        self._user_id = user_id

    def _not_connected(self) -> ProductDataUnavailableError:
        return self._unavailable("Сільпо не підключено: потрібен одноразовий вхід адміністратора")

    def _account_problem(self, exc: BaseException) -> ProductDataUnavailableError:
        if self._user_id is not None:
            return SilpoAccountUnusableError()
        if isinstance(exc, SilpoNotConnectedError):
            return self._not_connected()
        return self._unavailable()  # the service account has no store: Silpo-side setup

    async def _once[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        sessionmaker = get_sessionmaker()
        storage = (
            DbTokenStorage.for_user(sessionmaker, self._user_id)
            if self._user_id is not None
            else DbTokenStorage(sessionmaker)
        )
        async with connect(self._url, storage, interactive=False) as silpo:
            return await work(ProductCatalog(silpo))

    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        """`work` must only read: after an HTTP 429 it is run again on a fresh session. The
        deadline covers the retries too, so a throttling Silpo still ends in a 503, not a hang."""
        try:
            async with asyncio.timeout(LOOKUP_DEADLINE_SECONDS):
                for delay in (*HTTP_429_RETRY_DELAYS, None):
                    try:
                        return await self._once(work)
                    except BaseExceptionGroup as group:
                        if delay is None or group.subgroup(_is_http_429) is None:
                            raise
                        logger.warning("silpo answered HTTP 429, retrying in %ss", delay)
                        await asyncio.sleep(delay)
                raise AssertionError("unreachable: the retry loop returns or raises")
        except _ACCOUNT_PROBLEMS as exc:
            raise self._account_problem(exc) from exc
        except BaseExceptionGroup as group:
            # The MCP SDK runs the transport in an anyio task group, so errors raised inside
            # its callbacks (e.g. "no login stored") come out wrapped in an ExceptionGroup.
            account = group.subgroup(_ACCOUNT_PROBLEMS)
            if account is not None:
                raise self._account_problem(_first(account)) from group
            if group.subgroup(_EXPECTED) is not None:
                logger.warning("silpo lookup failed: %s", group)
                raise self._unavailable() from group
            if not isinstance(group, ExceptionGroup):
                raise  # holds a cancellation or another BaseException: never swallowed
            logger.exception("silpo lookup failed on an unexpected error")
            raise self._unavailable() from group
        except _EXPECTED as exc:
            logger.warning("silpo lookup failed: %s: %s", type(exc).__name__, exc)
            raise self._unavailable() from exc
        except ProductDataUnavailableError:
            raise  # already the clean answer (e.g. from a nested provider), keep its message
        except Exception as exc:
            # A Silpo reply we did not foresee (or a bug of ours reading it). The user gets the
            # same clean 503 as for "Silpo is down"; the traceback stays in the logs.
            logger.exception("silpo lookup failed on an unexpected error")
            raise self._unavailable() from exc


class UnconfiguredCatalogProvider:
    """No SILPO_MCP_URL: every lookup is "Silpo unavailable", so callers degrade the same way as
    when Silpo is down, instead of the whole endpoint failing before it starts."""

    async def run[T](self, work: Callable[[ProductCatalog], Awaitable[T]]) -> T:
        raise ProductDataUnavailableError("Сільпо не налаштовано (немає SILPO_MCP_URL)")


def get_catalog_provider(settings: Annotated[Settings, Depends(get_settings)]) -> CatalogProvider:
    if not settings.silpo_mcp_url:
        return UnconfiguredCatalogProvider()
    return ConnectedCatalogProvider(settings.silpo_mcp_url)


CatalogDep = Annotated[CatalogProvider, Depends(get_catalog_provider)]


class UserCatalogFactory(Protocol):
    """Builds a provider that searches as the given user (their store, their prices)."""

    def __call__(self, user_id: uuid.UUID) -> CatalogProvider: ...


def get_user_catalog_factory(
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserCatalogFactory:
    url = settings.silpo_mcp_url

    def build(user_id: uuid.UUID) -> CatalogProvider:
        if not url:
            return UnconfiguredCatalogProvider()
        return ConnectedCatalogProvider(url, user_id=user_id)

    return build


UserCatalogDep = Annotated[UserCatalogFactory, Depends(get_user_catalog_factory)]
