"""Thin, provider-agnostic structured-output client. Gemini is the only implementation today.

Practices baked in: system instruction separated from user data, JSON schema enforced by the
provider, Pydantic validation on our side, one corrective retry on invalid output, bounded
output tokens, thinking disabled for the cheap model, a short per-attempt deadline with one
fallback to a second model when the primary is slow or overloaded, and token usage logged
for cost tracking. Prompts are never logged in full.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol

from fastapi import Depends
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import LLMInvalidResponseError, LLMUnavailableError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = [408, 429, 500, 502, 503, 504]


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    data: T
    model: str
    prompt_tokens: int | None
    output_tokens: int | None
    latency_ms: int


class StructuredLLM(Protocol):
    """Anything that can turn a prompt into a validated Pydantic object."""

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]: ...


class GeminiLLM:
    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self._settings = settings
        self._client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.llm_timeout_seconds * 1000),
                # No SDK retries: a slow attempt is better abandoned for the fallback model
                # than retried against the same overloaded one.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    async def generate[T: BaseModel](
        self, *, system: str, user: str, schema: type[T], temperature: float | None = None
    ) -> LLMResult[T]:
        s = self._settings
        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=s.llm_temperature if temperature is None else temperature,
            max_output_tokens=s.llm_max_output_tokens,
            candidate_count=1,
            # Flash-Lite answers recipes fine without reasoning tokens; keep the cost at the floor.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        started = time.perf_counter()
        contents: list[types.ContentUnion] = [user]
        last_error: Exception | None = None
        model = s.gemini_model

        for attempt in range(2):
            response, model = await self._call_with_fallback(model, contents, config)

            usage = response.usage_metadata
            prompt_tokens = usage.prompt_token_count if usage else None
            output_tokens = usage.candidates_token_count if usage else None

            try:
                data = self._parse(response, schema)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "llm invalid output model=%s attempt=%d errors=%d",
                    s.gemini_model,
                    attempt + 1,
                    exc.error_count(),
                )
                # Ask the model to fix its own output once; cheaper than a cold retry.
                contents = [
                    user,
                    response.text or "",
                    f"Попередня відповідь не пройшла валідацію: {exc.errors()[:3]}. "
                    "Поверни виправлений JSON за схемою.",
                ]
                continue

            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "llm ok model=%s prompt_tokens=%s output_tokens=%s latency_ms=%d attempt=%d",
                model,
                prompt_tokens,
                output_tokens,
                latency_ms,
                attempt + 1,
            )
            return LLMResult(
                data=data,
                model=model,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )

        raise LLMInvalidResponseError() from last_error

    async def _call_with_fallback(
        self,
        model: str,
        contents: list[types.ContentUnion],
        config: types.GenerateContentConfig,
    ) -> tuple[types.GenerateContentResponse, str]:
        """One attempt on `model`; on timeout/overload one more on the fallback model.

        Returns the response and the model that actually produced it.
        """
        s = self._settings
        candidates = [model]
        if s.gemini_fallback_model and s.gemini_fallback_model != model:
            candidates.append(s.gemini_fallback_model)

        last_exc: Exception | None = None
        for name in candidates:
            try:
                async with asyncio.timeout(s.llm_timeout_seconds + 1):
                    response = await self._client.aio.models.generate_content(
                        model=name, contents=contents, config=config
                    )
                return response, name
            except (TimeoutError, genai_errors.ServerError) as exc:
                last_exc = exc
                logger.warning(
                    "llm slow/unavailable model=%s error=%s: %s", name, type(exc).__name__, exc
                )
            except genai_errors.ClientError as exc:
                if exc.code in RETRYABLE_STATUS:
                    last_exc = exc
                    logger.warning("llm rate limited model=%s code=%s", name, exc.code)
                    continue
                logger.error("llm client error model=%s code=%s", name, exc.code)
                raise LLMInvalidResponseError() from exc
        raise LLMUnavailableError() from last_exc

    @staticmethod
    def _parse[T: BaseModel](response: types.GenerateContentResponse, schema: type[T]) -> T:
        parsed = response.parsed
        if isinstance(parsed, schema):
            return parsed
        # Blocked, truncated or otherwise unparsed by the SDK: validate the raw text ourselves.
        return schema.model_validate_json(response.text or "")


@lru_cache
def get_llm() -> StructuredLLM:
    settings = get_settings()
    if not settings.gemini_api_key:
        # Surfaces as a clean 503 instead of a 500; lru_cache does not cache exceptions.
        raise LLMUnavailableError("Сервіс генерації не налаштовано (немає GEMINI_API_KEY)")
    return GeminiLLM(settings)


LLMDep = Annotated[StructuredLLM, Depends(get_llm)]
