"""Without a stored Silpo login the nutrition lookup must answer a clean 503, never a 500.

The MCP SDK wraps errors raised in its auth callbacks into an ExceptionGroup; this guards the
mapping that turns it back into NutritionUnavailableError.
"""

import asyncio

import pytest

from app.core.errors import NutritionUnavailableError
from app.integrations.silpo import SilpoNotConnectedError
from app.services import catalog
from app.services.nutrition import ConnectedSilpoProvider


class _RaisingConnect:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def __call__(self, *_: object, **__: object) -> "_RaisingConnect":
        return self

    async def __aenter__(self) -> None:
        raise self.exc

    async def __aexit__(self, *_: object) -> None:
        return None


@pytest.mark.parametrize(
    "exc",
    [
        SilpoNotConnectedError(),
        ExceptionGroup("unhandled errors in a TaskGroup", [SilpoNotConnectedError()]),
    ],
    ids=["plain", "inside-exception-group"],
)
async def test_missing_login_is_service_unavailable(
    monkeypatch: pytest.MonkeyPatch, exc: BaseException
) -> None:
    monkeypatch.setattr(catalog, "connect", _RaisingConnect(exc))
    monkeypatch.setattr(catalog, "get_sessionmaker", lambda: None)

    with pytest.raises(NutritionUnavailableError) as caught:
        await ConnectedSilpoProvider("https://mcp.silpo.ua/mcp").lookup(["яйця"])

    assert "не підключено" in caught.value.detail


async def test_unrelated_error_group_is_a_503_that_keeps_the_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    group = ExceptionGroup("boom", [KeyError("x")])
    monkeypatch.setattr(catalog, "connect", _RaisingConnect(group))
    monkeypatch.setattr(catalog, "get_sessionmaker", lambda: None)

    with pytest.raises(NutritionUnavailableError) as caught:
        await ConnectedSilpoProvider("https://mcp.silpo.ua/mcp").lookup(["яйця"])

    assert caught.value.__cause__ is group  # chained (and logged), not swallowed


async def test_a_cancelled_group_is_not_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    group = BaseExceptionGroup("boom", [asyncio.CancelledError(), KeyError("x")])
    monkeypatch.setattr(catalog, "connect", _RaisingConnect(group))
    monkeypatch.setattr(catalog, "get_sessionmaker", lambda: None)

    with pytest.raises(BaseExceptionGroup):
        await ConnectedSilpoProvider("https://mcp.silpo.ua/mcp").lookup(["яйця"])
