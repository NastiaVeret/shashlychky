"""Offline half of the suite: scripted provider answers replayed through the real `GeminiLLM`.

The point is to measure the guard rails rather than the model. Every scenario below is a shape
of broken answer we have actually seen (or that the provider can produce under load), and the
assertion is what the client must do about it: repair it with one corrective turn, or fail with
a clean error instead of a 500.
"""

import json
import time
from collections.abc import Sequence
from typing import Any

import httpx
from google.genai import errors as genai_errors

from app.core.config import Settings
from app.core.errors import AppError, LLMInvalidResponseError, LLMUnavailableError
from app.schemas.recipes import RecipeContent
from app.services.llm import GeminiLLM
from evals.cases import ScriptedCase
from evals.checks import CheckResult
from evals.runner import CaseRun

VALID_RECIPE: dict[str, Any] = {
    "title": "Омлет з помідорами",
    "description": "Швидкий сніданок з яєць і помідорів.",
    "cooking_time_minutes": 10,
    "servings": 2,
    "ingredients": [
        {"name": "Яйця", "quantity": 4, "unit": "шт", "have_at_home": True},
        {"name": "Помідор", "quantity": 1, "unit": "шт", "have_at_home": True},
        {"name": "Сіль", "quantity": None, "unit": "за смаком", "have_at_home": True},
    ],
    "steps": ["Збити яйця з сіллю.", "Нарізати помідор.", "Смажити 5 хвилин під кришкою."],
    "tips": None,
    "clarifying_question": None,
}


def _recipe(**overrides: Any) -> str:  # noqa: ANN401 - mirrors arbitrary model output
    return json.dumps(VALID_RECIPE | overrides, ensure_ascii=False)


def _with_ingredient(**overrides: Any) -> str:  # noqa: ANN401 - mirrors arbitrary model output
    ingredients = [VALID_RECIPE["ingredients"][0] | overrides, *VALID_RECIPE["ingredients"][1:]]
    return _recipe(ingredients=ingredients)


def _server_error(code: int) -> genai_errors.ServerError:
    return genai_errors.ServerError(code, {"error": {"message": "overloaded"}}, None)


SCRIPTED: list[ScriptedCase] = [
    ScriptedCase(
        id="valid_first_try",
        probes="a well-formed answer must not trigger a retry",
        responses=[_recipe()],
        expect_attempts=1,
    ),
    ScriptedCase(
        id="unknown_unit_then_valid",
        probes='invented unit ("жменя") - the retry must repair it',
        responses=[_with_ingredient(unit="жменя"), _recipe()],
        expect_attempts=2,
    ),
    ScriptedCase(
        id="missing_required_field",
        probes="dropped field - the retry must repair it",
        responses=[json.dumps({k: v for k, v in VALID_RECIPE.items() if k != "steps"}), _recipe()],
        expect_attempts=2,
    ),
    ScriptedCase(
        id="truncated_json",
        probes="output cut off by the token limit",
        responses=['{"title": "Омлет", "ingredi', _recipe()],
        expect_attempts=2,
    ),
    ScriptedCase(
        id="prose_instead_of_json",
        probes="the model answers in prose and ignores the schema",
        responses=["Звісно! Ось чудовий рецепт омлету: візьміть яйця...", _recipe()],
        expect_attempts=2,
    ),
    ScriptedCase(
        id="empty_answer",
        probes="blocked or empty candidate",
        responses=["", _recipe()],
        expect_attempts=2,
    ),
    ScriptedCase(
        id="broken_twice_gives_up",
        probes="two bad answers must end in a clean 502, never a 500",
        responses=[_with_ingredient(unit="жменя"), _recipe(servings=99)],
        expect_error=LLMInvalidResponseError,
    ),
    ScriptedCase(
        id="overloaded_primary_falls_back",
        probes="503 on the primary model must fall back, not fail",
        responses=[_server_error(503), _recipe()],
        expect_attempts=1,
        expect_model="fallback-model",
    ),
    ScriptedCase(
        id="both_models_down",
        probes="provider outage must surface as 503, not a crash",
        responses=[_server_error(503), _server_error(504)],
        expect_error=LLMUnavailableError,
    ),
    ScriptedCase(
        id="http_timeout_falls_back",
        probes="the SDK's own HTTP deadline fires before ours: httpx.ReadTimeout, not TimeoutError",
        responses=[httpx.ReadTimeout("read timed out"), _recipe()],
        expect_attempts=1,
        expect_model="fallback-model",
    ),
    ScriptedCase(
        id="http_timeout_on_both_models",
        probes="a slow provider must end in 503, never an uncaught httpx error",
        responses=[httpx.ReadTimeout("read timed out"), httpx.ConnectError("no route")],
        expect_error=LLMUnavailableError,
    ),
    ScriptedCase(
        id="quantity_as_string",
        probes="numbers sent as strings must be coerced, not rejected",
        responses=[_with_ingredient(quantity="4")],
        expect_attempts=1,
    ),
    ScriptedCase(
        id="kilograms_are_converted",
        probes="a scaled unit must be normalized without a retry",
        responses=[_with_ingredient(quantity=1.5, unit="кг")],
        expect_attempts=1,
    ),
    ScriptedCase(
        id="numbered_steps_are_cleaned",
        probes="the model numbering its own steps must not cost a retry",
        responses=[_recipe(steps=["1. Збити яйця.", "2. Смажити 5 хвилин."])],
        expect_attempts=1,
    ),
]


class _Usage:
    prompt_token_count = 11
    candidates_token_count = 22


class _Response:
    """Mimics the SDK response for text the SDK could not parse into the schema itself."""

    def __init__(self, text: str) -> None:
        self.parsed = None
        self.text = text
        self.usage_metadata = _Usage()


def scripted_llm(case: ScriptedCase) -> tuple[GeminiLLM, list[str]]:
    """A `GeminiLLM` whose provider call replays `case.responses`, plus the models it called."""
    settings = Settings(
        gemini_api_key="eval",
        gemini_model="primary-model",
        gemini_fallback_model="fallback-model",
        llm_timeout_seconds=5,
    )
    llm = GeminiLLM(settings)
    models_called: list[str] = []
    remaining = list(case.responses)

    async def fake_generate(*, model: str, contents: Any, config: Any) -> Any:  # noqa: ANN401
        models_called.append(model)
        if not remaining:
            raise AssertionError(f"{case.id}: provider called more times than scripted")
        answer = remaining.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return _Response(answer)

    llm._client.aio.models.generate_content = fake_generate  # type: ignore[assignment]
    return llm, models_called


async def run_scripted(case: ScriptedCase) -> CaseRun:
    """Replay one scenario and check the client reacted as the contract promises."""
    llm, models_called = scripted_llm(case)
    started = time.perf_counter()
    checks: list[CheckResult] = []
    try:
        result = await llm.generate(system="eval", user="eval", schema=RecipeContent)
    except AppError as exc:
        expected = case.expect_error is not None and isinstance(exc, case.expect_error)
        return CaseRun(
            case_id=case.id,
            probes=case.probes,
            generated=False,
            error=f"{type(exc).__name__}: {exc.detail}",
            attempts=len(models_called),
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=None,
            expected_failure=case.expect_error is not None,
            checks=[
                CheckResult(
                    "fails_as_specified",
                    expected,
                    f"expected {case.expect_error.__name__ if case.expect_error else 'success'}, "
                    f"got {type(exc).__name__}",
                )
            ],
        )

    checks.append(
        CheckResult(
            "no_unexpected_error", case.expect_error is None, "an error was expected but none came"
        )
    )
    checks.append(
        CheckResult(
            "attempts_as_specified",
            result.attempts == case.expect_attempts,
            f"expected {case.expect_attempts}, got {result.attempts}",
        )
    )
    if case.expect_model:
        checks.append(
            CheckResult(
                "model_as_specified",
                result.model == case.expect_model,
                f"expected {case.expect_model}, got {result.model}",
            )
        )
    return CaseRun(
        case_id=case.id,
        probes=case.probes,
        generated=True,
        error=None,
        attempts=result.attempts,
        latency_ms=result.latency_ms,
        model=result.model,
        checks=checks,
    )


async def run_scripted_suite(cases: Sequence[ScriptedCase] = tuple(SCRIPTED)) -> list[CaseRun]:
    return [await run_scripted(case) for case in cases]
