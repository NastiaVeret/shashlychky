"""Thin, provider-agnostic structured-output client. Gemini is the only implementation today.

Practices baked in: system instruction separated from user data, JSON schema enforced by the
provider, Pydantic validation on our side, one corrective retry on invalid output, bounded
output tokens, thinking disabled for the cheap model, SDK retries with backoff on 429/5xx,
an overall timeout, and token usage logged for cost tracking. Prompts are never logged in full.
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
                retry_options=types.HttpRetryOptions(
                    attempts=2,  # one retry; a second one would push the user past 40 s
                    initial_delay=0.5,
                    max_delay=2.0,
                    http_status_codes=RETRYABLE_STATUS,
                ),
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

        for attempt in range(2):
            try:
                # SDK may retry once, so the outer guard covers two attempts plus backoff.
                async with asyncio.timeout(s.llm_timeout_seconds * 2 + 3):
                    response = await self._client.aio.models.generate_content(
                        model=s.gemini_model, contents=contents, config=config
                    )
            except (TimeoutError, genai_errors.ServerError) as exc:
                logger.warning(
                    "llm unavailable model=%s error=%s: %s", s.gemini_model, type(exc).__name__, exc
                )
                raise LLMUnavailableError() from exc
            except genai_errors.ClientError as exc:
                if exc.code in RETRYABLE_STATUS:
                    logger.warning("llm rate limited model=%s code=%s", s.gemini_model, exc.code)
                    raise LLMUnavailableError() from exc
                logger.error("llm client error model=%s code=%s", s.gemini_model, exc.code)
                raise LLMInvalidResponseError() from exc

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
                s.gemini_model,
                prompt_tokens,
                output_tokens,
                latency_ms,
                attempt + 1,
            )
            return LLMResult(
                data=data,
                model=s.gemini_model,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
            )

        raise LLMInvalidResponseError() from last_error

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
