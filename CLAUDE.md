# Shashlychky

Monorepo: `backend/` (FastAPI, Python 3.13, uv) + `frontend/` (React 19, TypeScript, Vite).
Backend runs on Google Cloud Run with Cloud SQL Postgres, frontend on Firebase Hosting with `/api/**` rewritten to the backend (same origin).
Deployed via GitHub Actions (`.github/workflows/deploy.yml`); PRs get a Firebase preview channel (`preview.yml`).

Detailed per-area rules are loaded automatically from `.claude/rules/` (backend, frontend, git).
This file covers only what applies to the whole repo.

## Commands

```bash
# backend (from backend/)
uv sync                                  # install dependencies
docker compose up -d db                  # local Postgres (from repo root)
uv run alembic upgrade head              # apply migrations
uv run uvicorn app.main:app --reload     # http://localhost:8000/docs
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy app

# frontend (from frontend/)
npm install
npm run dev                              # http://localhost:5173, /api is proxied to :8000
npm run lint && npm run format:check && npm run build
```

Run everything at once: `/check`. Before opening a PR: `/pr`. Schema change: `/migration`.
Idiom guides: `python-best-practices` (backend) and `react-best-practices` (frontend) skills; consult them when writing or reviewing non-trivial code.
After a backend API change, use the `frontend-integrator` agent to bring the frontend types, request functions and hooks in sync.

## Language and style

- Identifiers, file names, comments, docstrings, commit messages, docs: English.
- User-facing UI text: Ukrainian (the product is for Ukrainian users).
- Talk to Claude in English or Ukrainian, whichever is convenient.
- No `print`/`console.log` debugging left in commits. Use `logging` in the backend.

## Architecture decisions

- The API is versioned: every route lives under `/api/v1/...` (`backend/app/api/v1/`).
- Configuration only via `Settings` (`backend/app/core/config.py`) and environment variables. Secrets are never committed; in production they come from Secret Manager.
- Database: PostgreSQL via SQLAlchemy 2 async + Alembic. Every schema change ships with a migration in the same PR; deploy runs migrations before the new revision starts, so migrations must be backward compatible (details in `.claude/rules/database.md`).
- The frontend talks to the backend only through `frontend/src/api/` and `@tanstack/react-query`. No raw `fetch` in components.
- API contract: a Pydantic model on the backend ↔ a TypeScript interface in `frontend/src/api/`. Change one, change the other.
- The backend container listens on `$PORT` (Cloud Run). Never hardcode ports in the Dockerfile.
- The frontend calls the API by relative path (`/api/v1/...`). `VITE_API_URL` stays empty in production; Vite proxies in dev, Firebase rewrites in prod.

## Workflow

1. Branch from `main`: `feat/...`, `fix/...`, `chore/...`.
2. Ship changes together with tests. A new endpoint without a test is not merged.
3. `/check` is green locally, then open a PR. CI runs the same checks.
4. Merging into `main` auto-deploys backend to Cloud Run and frontend to Firebase Hosting. Do not merge anything that is not production-ready; use a feature flag or a separate branch for half-done work.

## Do NOT do without discussing with the team

- Add dependencies "just in case". One library = one clear need.
- Change the folder structure, CI/CD, `firebase.json`, or the Dockerfile.
- Rewrite working code "for beauty" when the task is not about that.
