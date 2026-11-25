"""Thin, provider-agnostic structured-output client. Gemini is the only implementation today.

Practices baked in: system instruction separated from user data, JSON schema enforced by the
provider, Pydantic validation on our side, one corrective retry on invalid output, bounded
output tokens, thinking disabled for the cheap model, a short per-attempt deadline with a
chain of fallback models when the primary is slow or overloaded (a model that just failed is
skipped for a while), an overall deadline, and token usage logged for cost tracking. Prompts
are never logged in full.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Protocol

import httpx
from fastapi import Depends
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.core.errors import LLMInvalidResponseError, LLMUnavailableError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = [408, 429, 500, 502, 503, 504]
# A model that timed out or was overloaded goes to the back of the queue for this long, so the
# next requests do not each burn a full timeout on it first.
COOLDOWN_SECONDS = 60.0
# A model the API does not know (404) or that rejects our request (400) is retired for much
# longer: that will not fix itself.
MISSING_MODEL_COOLDOWN_SECONDS = 3600.0
ROUND_PAUSE_SECONDS = 2.0
# Not worth starting an attempt with less time than this left.
MIN_ATTEMPT_SECONDS = 2.0
# Hedging: a model that has not answered after this long gets company from the next model in
# the chain; the first valid answer wins and the rest are cancelled. Flash-Lite answers a recipe
# in 2-6 s, so a slower one is likely stuck in an overloaded queue.
HEDGE_AFTER_SECONDS = 6.0
MAX_PARALLEL_CALLS = 3


class _ModelFailedError(Exception):
    """One model could not serve this call; `retry_now` means try the same model again."""

    def __init__(self, cause: Exception, *, retry_now: bool = False) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.retry_now = retry_now


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    data: T
    model: str
    prompt_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    attempts: int = 1
    """How many model calls it took to get a valid object. >1 means a corrective retry fired."""


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
        self._cooldown_until: dict[str, float] = {}
        # Index into `_thinking_variants(model)`: advanced when a model rejects a thinking config.
        self._thinking_variant: dict[str, int] = {}
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
        deadline = time.monotonic() + s.llm_total_timeout_seconds
        contents: list[types.ContentUnion] = [user]
        last_error: Exception | None = None
        model: str | None = None

        for attempt in range(2):
            response, model = await self._call_with_fallback(model, contents, config, deadline)

            usage = response.usage_metadata
            prompt_tokens = usage.prompt_token_count if usage else None
            output_tokens = usage.candidates_token_count if usage else None

            try:
                data = self._parse(response, schema)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "llm invalid output model=%s attempt=%d errors=%d",
                    model,
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
                attempts=attempt + 1,
            )

        raise LLMInvalidResponseError() from last_error

    def _models(self) -> list[str]:
        s = self._settings
        names = [s.gemini_model, *s.gemini_fallback_models.replace(",", " ").split()]
        return list(dict.fromkeys(names))

    def _ordered_candidates(self, preferred: str | None) -> list[str]:
        """Healthy models in configured order first, then the ones cooling down.

        `preferred` (the model that produced the previous, invalid answer) goes first so the
        corrective retry talks to the same model that saw the conversation.
        """
        now = time.monotonic()
        models = self._models()
        healthy = [m for m in models if self._cooldown_until.get(m, 0.0) <= now]
        cooling = sorted(
            (m for m in models if m not in healthy), key=lambda m: self._cooldown_until[m]
        )
        ordered = healthy + cooling
        if preferred in ordered:
            ordered.remove(preferred)
            ordered.insert(0, preferred)
        return ordered

    def _cool_down(self, model: str, seconds: float = COOLDOWN_SECONDS) -> None:
        self._cooldown_until[model] = time.monotonic() + seconds

    async def _call_with_fallback(
        self,
        preferred: str | None,
        contents: list[types.ContentUnion],
        config: types.GenerateContentConfig,
        deadline: float,
    ) -> tuple[types.GenerateContentResponse, str]:
        """Get one answer from the model chain within `deadline` (time.monotonic()).

        Each pass races the chain with hedging (see `_race`); a failed pass is repeated after a
        short pause up to `llm_retry_rounds` times. Returns the response and its model.
        """
        s = self._settings
        last_exc: Exception | None = None
        for round_no in range(max(1, s.llm_retry_rounds)):
            if round_no:
                if deadline - time.monotonic() < ROUND_PAUSE_SECONDS + MIN_ATTEMPT_SECONDS:
                    break
                await asyncio.sleep(ROUND_PAUSE_SECONDS)
            result, exc = await self._race(
                self._ordered_candidates(preferred), contents, config, deadline
            )
            if result is not None:
                return result
            last_exc = exc or last_exc
        raise LLMUnavailableError() from last_exc

    async def _race(
        self,
        candidates: list[str],
        contents: list[types.ContentUnion],
        config: types.GenerateContentConfig,
        deadline: float,
    ) -> tuple[tuple[types.GenerateContentResponse, str] | None, Exception | None]:
        """Start models in order: the next one when a running call fails or is slower than
        HEDGE_AFTER_SECONDS, at most MAX_PARALLEL_CALLS at once. First success wins."""
        queue = deque(candidates)
        running: dict[asyncio.Task[types.GenerateContentResponse], str] = {}
        last_exc: Exception | None = None

        def launch() -> None:
            name = queue.popleft()
            task = asyncio.create_task(self._attempt(name, contents, config, deadline))
            running[task] = name

        try:
            while queue or running:
                remaining = deadline - time.monotonic()
                if remaining < MIN_ATTEMPT_SECONDS and not running:
                    break
                if not running:
                    launch()
                wait_for = max(remaining, 0.0)
                if queue and len(running) < MAX_PARALLEL_CALLS:
                    wait_for = min(wait_for, HEDGE_AFTER_SECONDS)
                done, _ = await asyncio.wait(
                    running, timeout=wait_for, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    if time.monotonic() >= deadline:
                        break
                    if queue and len(running) < MAX_PARALLEL_CALLS:
                        logger.info("llm slow, hedging with model=%s", queue[0])
                        launch()
                    continue
                for task in done:
                    name = running.pop(task)
                    try:
                        response = task.result()
                    except _ModelFailedError as failed:
                        last_exc = failed.cause
                        if failed.retry_now:
                            queue.appendleft(name)
                        # A failure frees a slot: start the next model right away.
                        if queue and running and len(running) < MAX_PARALLEL_CALLS:
                            launch()
                        continue
                    return (response, name), None
        finally:
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
        return None, last_exc

    async def _attempt(
        self,
        name: str,
        contents: list[types.ContentUnion],
        config: types.GenerateContentConfig,
        deadline: float,
    ) -> types.GenerateContentResponse:
        """One call to one model. Raises `_ModelFailedError` for anything another model may fix."""
        s = self._settings
        remaining = deadline - time.monotonic()
        try:
            async with asyncio.timeout(min(s.llm_timeout_seconds + 1, max(remaining, 0.1))):
                response = await self._client.aio.models.generate_content(
                    model=name, contents=contents, config=self._config_for(name, config)
                )
        # httpx errors are not asyncio.TimeoutError: the SDK's own HTTP deadline fires before
        # ours, and an uncaught ReadTimeout here would be a 500 instead of a 503.
        except (TimeoutError, httpx.TransportError, genai_errors.ServerError) as exc:
            self._cool_down(name)
            logger.warning(
                "llm slow/unavailable model=%s error=%s: %s", name, type(exc).__name__, exc
            )
            raise _ModelFailedError(exc) from exc
        except genai_errors.ClientError as exc:
            if exc.code in RETRYABLE_STATUS:
                self._cool_down(name)
                logger.warning("llm rate limited model=%s code=%s", name, exc.code)
                raise _ModelFailedError(exc) from exc
            if exc.code == 400 and self._next_thinking_variant(name):
                logger.warning("llm model=%s rejected thinking config, retrying without", name)
                raise _ModelFailedError(exc, retry_now=True) from exc
            # 404: the model is gone or not open to this key. 400: this model rejects our
            # request. Either way another model may still serve it; only key-level errors
            # (401/403) are the same for every model.
            if exc.code in (400, 404):
                self._cool_down(name, MISSING_MODEL_COOLDOWN_SECONDS)
                logger.error(
                    "llm model unusable, skipping model=%s code=%s: %s", name, exc.code, exc.message
                )
                raise _ModelFailedError(exc) from exc
            logger.error("llm client error model=%s code=%s", name, exc.code)
            raise LLMInvalidResponseError() from exc
        self._cooldown_until.pop(name, None)
        return response

    def _thinking_variants(self, model: str) -> list[types.ThinkingConfig | None]:
        """Ways to keep thinking (latency and cost) at the floor, most effective first.

        Gemini 2.x takes `thinking_budget=0`; 3.x models answer 400 to it and want
        `thinking_level` instead. Unknown models get tried in order; `None` (provider default)
        is the last resort so a model that rejects both still answers.
        """
        if model == self._settings.gemini_model:
            return [types.ThinkingConfig(thinking_budget=0), None]
        return [types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL), None]

    def _next_thinking_variant(self, model: str) -> bool:
        index = self._thinking_variant.get(model, 0)
        if index + 1 >= len(self._thinking_variants(model)):
            return False
        self._thinking_variant[model] = index + 1
        return True

    def _config_for(
        self, model: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentConfig:
        thinking = self._thinking_variants(model)[self._thinking_variant.get(model, 0)]
        return config.model_copy(update={"thinking_config": thinking})

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
