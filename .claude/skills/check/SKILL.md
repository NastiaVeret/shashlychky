---
name: check
description: Run every project check (ruff, mypy, pytest, oxlint, prettier, tsc/vite build) and report briefly. Use before a commit or PR, or when the user says "check", "run the tests", "is everything green".
allowed-tools: Bash(cd *), Bash(uv run *), Bash(npm run *)
---

# Full project check

Prefer the single entry point from the repo root; it runs backend, frontend and the API-contract check:

```bash
make check
```

If `make` is unavailable or you need to isolate a part, run the blocks below. Do not stop at the first failure: collect all failures, then report.

## Backend

```bash
cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy app && uv run pytest -q
```

## Frontend

```bash
cd frontend && npm run format:check && npm run lint && npm run build
```

## Report

- All green: one line "All checks passed" and a table: tool → status.
- Failures: for each one give `file:line` and the error in a fenced block. Suggest a fix, but do not apply it unless the user asked to fix.
- If only formatting failed, you may run `uv run ruff format .` / `npm run format` right away and say so.
