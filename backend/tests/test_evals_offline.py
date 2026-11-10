"""The offline eval suite as a test, so CI gates on it (risk R2).

The dataset and the assertions live in `evals/`; this file only drives them, so adding a
scenario there needs no change here.
"""

import pytest

from evals.cases import ScriptedCase
from evals.offline import SCRIPTED, run_scripted


@pytest.mark.parametrize("case", SCRIPTED, ids=lambda c: c.id)
async def test_scripted_scenario(case: ScriptedCase) -> None:
    run = await run_scripted(case)
    assert run.passed, f"{case.id} ({case.probes}): " + "; ".join(
        f"{c.name}: {c.detail}" for c in run.failures
    )
