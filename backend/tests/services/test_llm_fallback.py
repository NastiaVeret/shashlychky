"""Fallback behaviour of GeminiLLM, with the SDK call stubbed out."""

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from app.core.config import Settings
from app.core.errors import LLMInvalidResponseError, LLMUnavailableError
from app.schemas.recipes import RecipeContent
from app.services import llm as llm_module
from app.services.llm import GeminiLLM
from tests.conftest import SAMPLE_RECIPE


class _Usage:
    prompt_token_count = 11
    candidates_token_count = 22


class _Response:
    def __init__(self, parsed: Any) -> None:  # noqa: ANN401 - mimics the SDK object
        self.parsed = parsed
        self.text = parsed.model_dump_json()
        self.usage_metadata = _Usage()


def _server_error(code: int) -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": "boom"}}, None)


@pytest.fixture(autouse=True)
def _no_round_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_module, "ROUND_PAUSE_SECONDS", 0.0)


def _make_llm(
    behaviour: Callable[[str], Any], *, fallbacks: str = "fallback", rounds: int = 1
) -> tuple[GeminiLLM, list[str]]:
    settings = Settings(
        gemini_api_key="test",
        gemini_model="primary",
        gemini_fallback_models=fallbacks,
        llm_timeout_seconds=1,
        llm_retry_rounds=rounds,
    )
    llm = GeminiLLM(settings)
    calls: list[str] = []

    async def fake_generate(*, model: str, contents: Any, config: Any) -> Any:
        calls.append(model)
        return behaviour(model)

    llm._client.aio.models.generate_content = fake_generate  # type: ignore[method-assign]
    return llm, calls


async def test_primary_success_does_not_touch_fallback() -> None:
    llm, calls = _make_llm(lambda _m: _Response(SAMPLE_RECIPE))
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "primary"
    assert calls == ["primary"]


async def test_overloaded_primary_falls_back_once() -> None:
    def behaviour(model: str) -> Any:
        if model == "primary":
            raise _server_error(503)
        return _Response(SAMPLE_RECIPE)

    llm, calls = _make_llm(behaviour)
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "fallback"
    assert calls == ["primary", "fallback"]


async def test_fallback_call_uses_thinking_level_not_budget() -> None:
    """Gemini 3.x answers 400 to thinking_budget=0; fallbacks ask for minimal thinking instead."""
    settings = Settings(
        gemini_api_key="test",
        gemini_model="primary",
        gemini_fallback_models="fallback",
        llm_timeout_seconds=1,
    )
    llm = GeminiLLM(settings)
    configs: dict[str, Any] = {}

    async def fake_generate(*, model: str, contents: Any, config: Any) -> Any:
        configs[model] = config
        if model == "primary":
            raise _server_error(503)
        return _Response(SAMPLE_RECIPE)

    llm._client.aio.models.generate_content = fake_generate  # type: ignore[method-assign]
    await llm.generate(system="s", user="u", schema=RecipeContent)

    assert configs["primary"].thinking_config.thinking_budget == 0
    assert configs["fallback"].thinking_config.thinking_budget is None
    assert configs["fallback"].thinking_config.thinking_level == types.ThinkingLevel.MINIMAL


async def test_both_models_down_raises_unavailable() -> None:
    def behaviour(_model: str) -> Any:
        raise _server_error(504)

    llm, calls = _make_llm(behaviour)
    with pytest.raises(LLMUnavailableError):
        await llm.generate(system="s", user="u", schema=RecipeContent)
    assert calls == ["primary", "fallback"]


async def test_chain_walks_past_missing_and_overloaded_models() -> None:
    def behaviour(model: str) -> Any:
        if model == "primary":
            raise TimeoutError
        if model == "gone":
            raise genai_errors.ClientError(404, {"error": {"message": "not found"}}, None)
        return _Response(SAMPLE_RECIPE)

    llm, calls = _make_llm(behaviour, fallbacks="gone, third")
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "third"
    assert calls == ["primary", "gone", "third"]


async def test_second_round_recovers_after_a_blip() -> None:
    failures = {"primary": 1, "fallback": 1}

    def behaviour(model: str) -> Any:
        if failures[model]:
            failures[model] -= 1
            raise _server_error(503)
        return _Response(SAMPLE_RECIPE)

    llm, calls = _make_llm(behaviour, rounds=2)
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "primary"
    assert calls == ["primary", "fallback", "primary"]


async def test_failed_model_is_skipped_on_the_next_request() -> None:
    def behaviour(model: str) -> Any:
        if model == "primary":
            raise _server_error(503)
        return _Response(SAMPLE_RECIPE)

    llm, calls = _make_llm(behaviour)
    await llm.generate(system="s", user="u", schema=RecipeContent)
    calls.clear()
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "fallback"
    assert calls == ["fallback"]


async def test_model_rejecting_the_request_is_skipped() -> None:
    def behaviour(model: str) -> Any:
        if model == "primary":
            raise genai_errors.ClientError(400, {"error": {"message": "bad"}}, None)
        return _Response(SAMPLE_RECIPE)

    llm, calls = _make_llm(behaviour)
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "fallback"
    # Once with the thinking config, once without it, then the next model.
    assert calls == ["primary", "primary", "fallback"]


async def test_thinking_config_rejection_retries_same_model_without_it() -> None:
    settings = Settings(
        gemini_api_key="test",
        gemini_model="primary",
        gemini_fallback_models="fallback",
        llm_timeout_seconds=1,
        llm_retry_rounds=1,
    )
    llm = GeminiLLM(settings)
    seen: list[tuple[str, Any]] = []

    async def fake_generate(*, model: str, contents: Any, config: Any) -> Any:
        seen.append((model, config.thinking_config))
        if model == "primary":
            raise _server_error(503)
        if config.thinking_config is not None:
            raise genai_errors.ClientError(400, {"error": {"message": "thinking"}}, None)
        return _Response(SAMPLE_RECIPE)

    llm._client.aio.models.generate_content = fake_generate  # type: ignore[method-assign]
    result = await llm.generate(system="s", user="u", schema=RecipeContent)
    assert result.model == "fallback"
    assert [m for m, _ in seen] == ["primary", "fallback", "fallback"]
    assert seen[-1][1] is None


async def test_slow_model_is_hedged_and_fastest_answer_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_module, "HEDGE_AFTER_SECONDS", 0.05)
    settings = Settings(
        gemini_api_key="test",
        gemini_model="primary",
        gemini_fallback_models="fallback",
        llm_timeout_seconds=5,
        llm_retry_rounds=1,
    )
    llm = GeminiLLM(settings)
    calls: list[str] = []
    primary_cancelled = asyncio.Event()

    async def fake_generate(*, model: str, contents: Any, config: Any) -> Any:
        calls.append(model)
        if model == "primary":
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                primary_cancelled.set()
                raise
        return _Response(SAMPLE_RECIPE)

    llm._client.aio.models.generate_content = fake_generate  # type: ignore[method-assign]
    result = await asyncio.wait_for(
        llm.generate(system="s", user="u", schema=RecipeContent), timeout=2
    )
    assert result.model == "fallback"
    assert calls == ["primary", "fallback"]
    assert primary_cancelled.is_set()


async def test_key_level_client_error_is_not_masked() -> None:
    def behaviour(_model: str) -> Any:
        raise genai_errors.ClientError(403, {"error": {"message": "denied"}}, None)

    llm, calls = _make_llm(behaviour)
    with pytest.raises(LLMInvalidResponseError):
        await llm.generate(system="s", user="u", schema=RecipeContent)
    assert calls == ["primary"]
