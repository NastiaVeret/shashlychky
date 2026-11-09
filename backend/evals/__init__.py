"""Eval suite for the recipe LLM (risk R2: hallucinations and broken JSON structure).

Two modes, same dataset and the same checks:

* **offline** (`python -m evals`) replays scripted model answers through the real `GeminiLLM`,
  so validation, the corrective retry and the model fallback are measured deterministically.
  Free, no network, runs in CI via `tests/test_evals_offline.py`.
* **live** (`python -m evals --live`) sends every case to the real Gemini and repeats it, which
  is what produces the stability numbers in `docs/STABILITY.md`.
"""
