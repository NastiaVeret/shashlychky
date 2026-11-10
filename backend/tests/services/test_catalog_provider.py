"""ConnectedCatalogProvider: every way Silpo can fail ends in a 503, a slow Silpo cannot hang."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest

from app.core.errors import NutritionUnavailableError, ProductDataUnavailableError
from app.integrations.silpo import SilpoError
from app.integrations.silpo.catalog import ProductCatalog
from app.services import catalog as catalog_service
from app.services.catalog import ConnectedCatalogProvider
from app.services.nutrition import ConnectedSilpoProvider


class SlowOrBrokenSilpo:
    def __init__(self, *, delay: float = 0, fail: bool = False) -> None:
        self.delay, self.fail = delay, fail

    async def search_context(self) -> dict[str, Any]:
        await asyncio.sleep(self.delay)
        if self.fail:
            raise SilpoError("silpo_get_time_slots", "down")
        return {"branchId": "b", "deliveryType": "DeliveryHome"}


@pytest.fixture
def silpo(monkeypatch: pytest.MonkeyPatch) -> SlowOrBrokenSilpo:
    fake = SlowOrBrokenSilpo()

    @asynccontextmanager
    async def fake_connect(*_: object, **__: object):  # type: ignore[no-untyped-def]
        yield fake

    monkeypatch.setattr(catalog_service, "connect", fake_connect)
    monkeypatch.setattr(catalog_service, "get_sessionmaker", lambda: None)
    return fake


async def test_run_hands_the_work_a_catalog_over_the_session(silpo: SlowOrBrokenSilpo) -> None:
    async def work(catalog: ProductCatalog) -> dict[str, Any]:
        return await catalog.context()

    ctx = await ConnectedCatalogProvider("https://x").run(work)
    assert ctx["branchId"] == "b"


async def test_silpo_error_becomes_service_unavailable(silpo: SlowOrBrokenSilpo) -> None:
    silpo.fail = True
    with pytest.raises(ProductDataUnavailableError):
        await ConnectedCatalogProvider("https://x").run(lambda catalog: catalog.context())


async def test_slow_silpo_ends_in_unavailable_not_a_hang(
    silpo: SlowOrBrokenSilpo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog_service, "LOOKUP_DEADLINE_SECONDS", 0.05)
    silpo.delay = 1
    with pytest.raises(ProductDataUnavailableError):
        await ConnectedCatalogProvider("https://x").run(lambda catalog: catalog.context())


async def test_nutrition_keeps_its_own_503_message(silpo: SlowOrBrokenSilpo) -> None:
    silpo.fail = True
    with pytest.raises(NutritionUnavailableError) as caught:
        await ConnectedSilpoProvider("https://x").lookup(["молоко"])
    assert "КБЖВ" in caught.value.detail


def _http_429() -> BaseExceptionGroup[httpx.HTTPStatusError]:
    """What the MCP transport raises on a real HTTP 429 (measured against a local server)."""
    request = httpx.Request("POST", "https://mcp.test/mcp")
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)
    return ExceptionGroup("unhandled errors in a TaskGroup", [error])


@pytest.fixture
def no_pause(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    pauses: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        # asyncio.sleep is patched globally; sleep(0) is the event loop yielding, not a retry pause
        if seconds:
            pauses.append(seconds)

    monkeypatch.setattr(catalog_service.asyncio, "sleep", fake_sleep)
    return pauses


def _fail_then_work(monkeypatch: pytest.MonkeyPatch, failures: int) -> list[int]:
    attempts: list[int] = []

    @asynccontextmanager
    async def flaky_connect(*_: object, **__: object):  # type: ignore[no-untyped-def]
        attempts.append(1)
        if len(attempts) <= failures:
            raise _http_429()
        yield SlowOrBrokenSilpo()

    monkeypatch.setattr(catalog_service, "connect", flaky_connect)
    monkeypatch.setattr(catalog_service, "get_sessionmaker", lambda: None)
    return attempts


async def test_http_429_is_retried_on_a_fresh_session(
    monkeypatch: pytest.MonkeyPatch, no_pause: list[float]
) -> None:
    attempts = _fail_then_work(monkeypatch, failures=2)

    result = await ConnectedCatalogProvider("https://mcp.test/mcp").run(lambda c: c.context())

    assert result["branchId"] == "b" and len(attempts) == 3
    assert no_pause == [1.0, 3.0]


async def test_persistent_http_429_ends_in_unavailable(
    monkeypatch: pytest.MonkeyPatch, no_pause: list[float]
) -> None:
    attempts = _fail_then_work(monkeypatch, failures=99)

    with pytest.raises(ProductDataUnavailableError):
        await ConnectedCatalogProvider("https://mcp.test/mcp").run(lambda c: c.context())

    assert len(attempts) == 3  # first try plus the two retries, then it gives up


# ---------- a reply we did not foresee: a clean 503, never a 500 ----------


def _fails_with(exc: BaseException) -> Callable[[ProductCatalog], Awaitable[None]]:
    async def work(catalog: ProductCatalog) -> None:
        raise exc

    return work


@pytest.mark.parametrize(
    "error",
    [
        AttributeError("'list' object has no attribute 'get'"),
        KeyError("shipments"),
        ZeroDivisionError("float division by zero"),
        # the MCP transport's task group, sometimes nested in another one
        ExceptionGroup("tg", [AttributeError("'list' object has no attribute 'get'")]),
        ExceptionGroup("outer", [ExceptionGroup("inner", [TypeError("list indices")])]),
    ],
)
async def test_an_unexpected_error_becomes_unavailable_and_is_logged(
    silpo: SlowOrBrokenSilpo, caplog: pytest.LogCaptureFixture, error: Exception
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(ProductDataUnavailableError):
        await ConnectedCatalogProvider("https://x").run(_fails_with(error))

    # logged with the traceback, so the bug behind it stays visible
    (record,) = [r for r in caplog.records if r.name == catalog_service.logger.name]
    assert record.exc_info is not None


async def test_an_unexpected_error_keeps_the_providers_own_message(
    silpo: SlowOrBrokenSilpo,
) -> None:
    with pytest.raises(NutritionUnavailableError):
        await ConnectedCatalogProvider("https://x", NutritionUnavailableError).run(
            _fails_with(AttributeError("boom"))
        )


@pytest.mark.parametrize(
    "error",
    [
        asyncio.CancelledError(),
        BaseExceptionGroup("tg", [asyncio.CancelledError(), AttributeError("boom")]),
    ],
)
async def test_cancellation_is_never_swallowed(
    silpo: SlowOrBrokenSilpo, error: BaseException
) -> None:
    with pytest.raises(type(error)):
        await ConnectedCatalogProvider("https://x").run(_fails_with(error))
