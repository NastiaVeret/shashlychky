"""Runs the suite and turns the results into stability metrics.

Stability, not just correctness, is the question: the same prompt sent twice can give different
answers, so every live case is repeated and we report how often it holds up. A case that passes
4 times out of 5 is a different kind of problem from one that never passes, and the report
separates them.
"""

import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.errors import AppError
from app.schemas.recipes import RecipeContent
from app.services.llm import StructuredLLM
from app.services.recipes import SYSTEM_PROMPT, build_user_prompt
from evals.cases import CASES, EvalCase
from evals.checks import CheckResult, run_checks


@dataclass(frozen=True, slots=True)
class CaseRun:
    case_id: str
    probes: str
    generated: bool
    """False when the client gave up: an invalid structure after the retry, or a provider outage."""

    error: str | None
    attempts: int
    latency_ms: int
    model: str | None
    checks: list[CheckResult] = field(default_factory=list)
    expected_failure: bool = False
    """Set when not generating *is* the correct outcome (an offline scenario that must fail)."""

    @property
    def passed(self) -> bool:
        # A run with no checks never produced anything to judge, so it cannot have passed.
        return bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


async def run_case(llm: StructuredLLM, case: EvalCase) -> CaseRun:
    """One generation through the production prompt and the production client."""
    prompt = build_user_prompt(case.request, case.profile)
    started = time.perf_counter()
    try:
        result = await llm.generate(system=SYSTEM_PROMPT, user=prompt, schema=RecipeContent)
    except AppError as exc:
        return CaseRun(
            case_id=case.id,
            probes=case.probes,
            generated=False,
            error=f"{type(exc).__name__}: {exc.detail}",
            attempts=0,
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=None,
        )
    return CaseRun(
        case_id=case.id,
        probes=case.probes,
        generated=True,
        error=None,
        attempts=result.attempts,
        latency_ms=result.latency_ms,
        model=result.model,
        checks=run_checks(case, result.data),
    )


async def run_suite(
    llm: StructuredLLM, cases: Sequence[EvalCase] = tuple(CASES), repeats: int = 1
) -> list[CaseRun]:
    """Every case `repeats` times, sequentially: the point is a stable measurement, not speed,
    and a burst of parallel calls would measure the provider's rate limiter instead."""
    runs: list[CaseRun] = []
    for _ in range(repeats):
        for case in cases:
            runs.append(await run_case(llm, case))
    return runs


@dataclass(frozen=True, slots=True)
class CaseSummary:
    case_id: str
    probes: str
    runs: int
    passed: int
    failed_checks: dict[str, int]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs if self.runs else 0.0

    @property
    def flaky(self) -> bool:
        """Sometimes right, sometimes wrong: the signature of an unstable prompt."""
        return 0 < self.passed < self.runs


@dataclass(frozen=True, slots=True)
class Metrics:
    generated_at: str
    total_runs: int
    generated: int
    expected_failures: int
    passed: int
    retried: int
    latency_p50_ms: int
    latency_p95_ms: int
    check_pass_rate: dict[str, float]
    cases: list[CaseSummary]
    errors: dict[str, int]

    @property
    def generation_rate(self) -> float:
        """Share of runs that produced a valid object, ignoring the ones meant to fail."""
        expected_to_generate = self.total_runs - self.expected_failures
        return self.generated / expected_to_generate if expected_to_generate else 0.0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_runs if self.total_runs else 0.0

    @property
    def retry_rate(self) -> float:
        return self.retried / self.generated if self.generated else 0.0

    @property
    def flaky_cases(self) -> list[CaseSummary]:
        return [c for c in self.cases if c.flaky]


def _percentile(values: list[int], share: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(int(len(ordered) * share), len(ordered) - 1)
    return ordered[index]


def summarize(runs: Sequence[CaseRun]) -> Metrics:
    by_case: dict[str, list[CaseRun]] = {}
    for run in runs:
        by_case.setdefault(run.case_id, []).append(run)

    cases: list[CaseSummary] = []
    for case_id, case_runs in by_case.items():
        failed: dict[str, int] = {}
        for run in case_runs:
            for check in run.failures:
                failed[check.name] = failed.get(check.name, 0) + 1
            # Nothing came back and no check explains why: the generation itself is the failure.
            if not run.generated and not run.checks:
                failed["generation"] = failed.get("generation", 0) + 1
        cases.append(
            CaseSummary(
                case_id=case_id,
                probes=case_runs[0].probes,
                runs=len(case_runs),
                passed=sum(1 for r in case_runs if r.passed),
                failed_checks=failed,
            )
        )

    totals: dict[str, list[bool]] = {}
    for run in runs:
        for check in run.checks:
            totals.setdefault(check.name, []).append(check.passed)

    errors: dict[str, int] = {}
    for run in runs:
        if run.error:
            kind = run.error.split(":")[0]
            errors[kind] = errors.get(kind, 0) + 1

    latencies = [r.latency_ms for r in runs if r.generated]
    return Metrics(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        total_runs=len(runs),
        generated=sum(1 for r in runs if r.generated),
        expected_failures=sum(1 for r in runs if r.expected_failure),
        passed=sum(1 for r in runs if r.passed),
        retried=sum(1 for r in runs if r.generated and r.attempts > 1),
        latency_p50_ms=int(statistics.median(latencies)) if latencies else 0,
        latency_p95_ms=_percentile(latencies, 0.95),
        check_pass_rate={
            name: sum(results) / len(results) for name, results in sorted(totals.items())
        },
        cases=sorted(cases, key=lambda c: (c.pass_rate, c.case_id)),
        errors=errors,
    )


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def render_markdown(metrics: Metrics, *, mode: str, model: str) -> str:
    """The report that backs the stability assessment in docs/STABILITY.md."""
    lines = [
        f"# Eval report ({mode})",
        "",
        f"- Дата: {metrics.generated_at}",
        f"- Модель: `{model}`",
        f"- Запусків: {metrics.total_runs} ({len(metrics.cases)} кейсів)",
        "",
        "## Підсумок",
        "",
        "| Метрика | Значення |",
        "|---|---|",
        f"| Відповідь отримано (структура валідна) | {_pct(metrics.generation_rate)} |",
        f"| Усі перевірки пройдено | {_pct(metrics.pass_rate)} |",
        f"| Знадобився retry | {_pct(metrics.retry_rate)} |",
    ]
    if metrics.latency_p95_ms:
        lines.append(
            f"| Латентність p50 / p95 | {metrics.latency_p50_ms} / {metrics.latency_p95_ms} мс |"
        )
    lines += [
        f"| Нестабільні кейси | {len(metrics.flaky_cases)} |",
        "",
        "## Перевірки",
        "",
        "| Перевірка | Пройдено |",
        "|---|---|",
    ]
    lines += [f"| `{name}` | {_pct(rate)} |" for name, rate in metrics.check_pass_rate.items()]
    lines += [
        "",
        "## Кейси",
        "",
        "| Кейс | Що перевіряє | Пройдено | Провалені перевірки |",
        "|---|---|---|---|",
    ]
    for case in metrics.cases:
        failed = ", ".join(f"`{n}` ×{c}" for n, c in sorted(case.failed_checks.items())) or "—"
        lines.append(f"| `{case.case_id}` | {case.probes} | {case.passed}/{case.runs} | {failed} |")
    if metrics.errors:
        lines += ["", "## Помилки", ""]
        lines += [f"- `{kind}`: {count}" for kind, count in sorted(metrics.errors.items())]
    return "\n".join(lines) + "\n"
