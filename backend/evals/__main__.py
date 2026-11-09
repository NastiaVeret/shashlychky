"""CLI: `python -m evals` (offline) or `python -m evals --live --repeats 3`.

Offline needs nothing. Live needs GEMINI_API_KEY and costs one model call per case per repeat.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import get_settings
from app.services.llm import GeminiLLM
from evals.cases import CASES, CASES_BY_ID
from evals.offline import run_scripted_suite
from evals.runner import CaseRun, render_markdown, run_suite, summarize


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="evals", description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="send the dataset to the real model (costs money)"
    )
    parser.add_argument(
        "--repeats", type=int, default=1, help="how many times to run each live case"
    )
    parser.add_argument("--case", action="append", help="run only these case ids")
    parser.add_argument("--out", type=Path, help="write the markdown report here")
    return parser.parse_args()


async def _live_runs(repeats: int, only: list[str] | None) -> tuple[list[CaseRun], str]:
    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set; live evals need it (backend/.env)")
    cases = [CASES_BY_ID[c] for c in only] if only else CASES
    runs = await run_suite(GeminiLLM(settings), cases, repeats=repeats)
    return runs, settings.gemini_model


def main() -> int:
    args = _parse_args()
    if args.live:
        runs, model = asyncio.run(_live_runs(args.repeats, args.case))
        mode = f"live ×{args.repeats}"
    else:
        runs = asyncio.run(run_scripted_suite())
        model, mode = "scripted (offline)", "offline"

    metrics = summarize(runs)
    report = render_markdown(metrics, mode=mode, model=model)
    print(report)
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"✔ written to {args.out}")

    failed = [c for c in metrics.cases if c.pass_rate < 1]
    if failed:
        print(f"✖ {len(failed)} case(s) did not pass every run", file=sys.stderr)
    return 1 if failed and not args.live else 0


if __name__ == "__main__":
    raise SystemExit(main())
