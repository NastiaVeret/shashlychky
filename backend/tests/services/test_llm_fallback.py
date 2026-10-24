"""Fallback behaviour of GeminiLLM, with the SDK call stubbed out."""

from collections.abc import Callable
from typing import Any

import pytest
from google.genai import errors as genai_errors

from app.core.config import Settings
from app.core.errors import LLMUnavailableError
from app.schemas.recipes import RecipeContent
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


def _make_llm(behaviour: Callable[[str], Any]) -> tuple[GeminiLLM, list[str]]:
    settings = Settings(
        gemini_api_key="test",
        gemini_model="primary",
        gemini_fallback_model="fallback",
        llm_timeout_seconds=1,
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


async def test_both_models_down_raises_unavailable() -> None:
    def behaviour(_model: str) -> Any:
        raise _server_error(504)

    llm, calls = _make_llm(behaviour)
    with pytest.raises(LLMUnavailableError):
        await llm.generate(system="s", user="u", schema=RecipeContent)
    assert calls == ["primary", "fallback"]
