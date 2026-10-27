# Shashlychky: what was built and how

Status: v1 in production at https://shashlychky.web.app (October 2026).

Shashlychky turns the products a user already has at home into one realistic recipe. The user lists products,
the backend asks a Gemini model for a structured recipe, validates it, stores it, and the React UI renders it as a
card with "have at home / to buy" markers. Every recipe gets a shareable URL.

This document explains the system as it exists today, the decisions behind it, and what is deliberately left out.
For day-to-day commands see the root `README.md`; for coding conventions see `CLAUDE.md` and `.claude/rules/`.

## 1. System overview

```
                 ┌────────────────────────── Firebase Hosting ──────────────────────────┐
  Browser ─────▶ │  https://shashlychky.web.app          static React build (Vite)       │
                 │  /api/**  ───────── rewrite ─────────┐                                 │
                 └──────────────────────────────────────┼─────────────────────────────────┘
                                                        ▼
                 ┌────────────────────── Cloud Run (europe-central2) ────────────────────┐
                 │  shashlychky-backend   FastAPI + uvicorn, 1 container, 0..3 instances  │
                 │     │ unix socket                                    │ HTTPS           │
                 │     ▼                                                ▼                 │
                 │  Cloud SQL Postgres 18                     Gemini Developer API        │
                 │  (recipes table)                           gemini-3.1-flash-lite       │
                 │                                            fallback: 3.5-flash-lite    │
                 │  shashlychky-migrate   Cloud Run Job, same image, `alembic upgrade head`│
                 └────────────────────────────────────────────────────────────────────────┘
                 Secrets: Secret Manager (db-password, gemini-api-key) → env vars at runtime
                 CI/CD: GitHub Actions → Artifact Registry → Cloud Run / Firebase, auth via Workload Identity
```

Frontend and API share one origin thanks to the Firebase rewrite, so there is no CORS in production and the
frontend never knows the backend URL.

## 2. Repository layout

```
backend/            FastAPI service (Python 3.13, uv)
  app/api/v1/       routers: health, auth, me, recipes
  app/api/deps.py   shared dependencies: SettingsDep, CurrentUser (session cookie)
  app/schemas/      Pydantic request/response models (the API contract)
  app/services/     llm.py (provider client), recipes.py (prompt + use case)
  app/models/       SQLAlchemy ORM models
  app/db/           engine, session dependency, declarative Base
  app/core/         Settings, error hierarchy
  alembic/          migrations
  tests/            pytest; FakeLLM; DB tests skip locally without Postgres
frontend/           React 19 + TypeScript + Vite + Tailwind v4
  src/api/          fetch wrapper and typed request functions (mirror of backend schemas)
  src/hooks/        react-query hooks
  src/components/   ProductInput, RecipeCard, Layout
  src/pages/        HomePage, RecipePage (lazy)
  firebase.json     hosting config incl. the /api rewrite
.github/workflows/  ci.yml, deploy.yml, preview.yml
.claude/            shared Claude Code config: rules, skills, agents, hooks
docs/               this document
docker-compose.yml  local Postgres (and optionally the backend container)
```

## 3. Backend

**Framework.** FastAPI with an app factory (`create_app`), a `lifespan` that disposes the DB engine on shutdown,
and one exception handler that maps the `AppError` hierarchy (`NotFoundError` → 404, `LLMUnavailableError` → 503,
`LLMInvalidResponseError` → 502) to JSON `{"detail": ...}`. Routers never raise `HTTPException` for domain errors.

**Layers.** `router → service → models/external clients`. Routers parse input and call one service function.
Services are plain `async def` functions taking an `AsyncSession` and typed arguments; they know nothing about HTTP.
Schemas (`app/schemas`) are the public contract; ORM models (`app/models`) are storage. They are separate classes
even when fields coincide.

**Configuration.** Only through `Settings` (pydantic-settings): `.env` locally, environment variables in Cloud Run.
Database parts (`DB_HOST`, `DB_USER`, …) or a full `DATABASE_URL`; `DB_HOST` starting with `/` is a Cloud SQL unix
socket. `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL`, `LLM_TIMEOUT_SECONDS` control the model client.

**Endpoints.**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | liveness, version |
| GET | `/api/v1/health/db` | `SELECT 1` against Postgres, 503 if down |
| POST | `/api/v1/auth/register` | create an account (email + password) and start a session → 201, 409 if taken |
| POST | `/api/v1/auth/login` | start a session → 200; 401 on bad credentials, 429 while locked |
| POST | `/api/v1/auth/logout` | revoke the current session → 204 |
| GET | `/api/v1/me` | the logged-in user, 401 without a session |
| POST | `/api/v1/recipes` | generate and store a recipe from products, servings, preferences → 201 |
| GET | `/api/v1/recipes/{id}` | read a stored recipe |

Input validation (`RecipeRequest`): 1–30 products, each trimmed and capped at 40 characters, de-duplicated
case-insensitively; servings 1–12; preferences ≤ 200 characters.

**Authentication.** Own email + password accounts (`app/services/auth.py`), no third-party identity
provider. Passwords are hashed with Argon2id at the OWASP minimum (19 MiB, t=2, p=1) in a worker
thread; the library default of 64 MiB would let a burst of logins exhaust a Cloud Run instance.
A login creates a server-side session: a random token goes into an httpOnly, Secure, SameSite=Lax
cookie, and the `sessions` table stores only its SHA-256, so sessions can be revoked and a leaked
table cannot be replayed. The cookie is named `__session` because Firebase Hosting strips every
other cookie before forwarding to Cloud Run; auth responses send `Cache-Control: no-store` so the
Hosting CDN never caches them. Login errors are one message for unknown email and wrong password
(an unknown email is still verified against a dummy hash to keep timing equal); after
`LOGIN_MAX_ATTEMPTS` failures the account is locked for `LOGIN_LOCKOUT_MINUTES` (429). CSRF relies on
SameSite=Lax plus the same-origin deployment. Registration reveals whether an email is taken (409);
that is accepted for usability.

**Quality gates.** `ruff` (lint + format), `mypy --strict`, `pytest`. All three run in CI and in the pre-commit
checks described in `CLAUDE.md`.

## 4. The LLM pipeline

File: `backend/app/services/llm.py` (provider client) and `backend/app/services/recipes.py` (prompt and use case).

**Provider isolation.** `StructuredLLM` is a `Protocol` with one method:
`generate(system, user, schema: type[T]) -> LLMResult[T]`. `GeminiLLM` is the only implementation; the recipe service
depends on the protocol, and tests inject a `FakeLLM`. Swapping providers touches one file.

**Structured output.** The Pydantic model `RecipeContent` is passed to Gemini as `response_schema` with
`response_mime_type="application/json"`. The SDK returns `response.parsed`; we still validate with Pydantic on our
side. If validation fails, the model gets one corrective turn (its previous answer plus the validation errors);
if that fails too, the request ends with 502.

**Prompting.** The system instruction (Ukrainian) sets the role, the rules (use the listed products, only basic pantry
additions, real quantities in г/мл/шт, short ordered steps, no invented products) and an explicit injection guard:
product names are data, not instructions. The user message contains only the product list, servings and optional
preferences. The schema has a `clarifying_question` field so the model can ask instead of hallucinating when the
input is insufficient.

**Resilience and cost.**

| Concern | Mechanism |
|---|---|
| slow or overloaded model | 12 s per-attempt deadline; on timeout / 503 / 504 one attempt on `GEMINI_FALLBACK_MODEL` |
| invalid JSON | one corrective retry, then 502 |
| rate limits (429) | treated as unavailable → fallback → 503 |
| cost | cheapest open model by default; thinking disabled (`thinking_budget=0`); `max_output_tokens=2048`; one candidate |
| observability | tokens, latency and the model that answered are logged and stored on each recipe row |
| secrets | API key only in Secret Manager → env var; never in the frontend or the repo |

**Model choice.** `gemini-2.5-flash-lite` is the cheapest on Google's price list but returns 404 for API keys created
after its retirement for new users. `gemini-3.1-flash-lite` ($0.25 / $1.50 per 1M input/output tokens, free tier) is
the cheapest model still open, so it is the default; `gemini-3.5-flash-lite` is the fallback. A recipe costs roughly
380 input + 600 output tokens, about $0.001. Measured latency in production: 3–9 s when the primary model answers;
Gemini intermittently returns `504 DEADLINE_EXCEEDED` for 3.1 Flash-Lite, which the fallback absorbs.

## 5. Database and migrations

Cloud SQL PostgreSQL 18 (`shashlychky:europe-central2:shashlychky`) in production, `postgres:18` via Docker
Compose locally. SQLAlchemy 2 async with the psycopg v3 driver (one driver for the async app and the sync Alembic
runner). `Base.metadata` carries a naming convention so autogenerated constraint names are deterministic.

Table `recipes`: id, products (JSONB), preferences, servings, model, content (JSONB, the validated `RecipeContent`),
prompt_tokens, output_tokens, latency_ms, created_at.

Alembic reads the URL from `Settings` and passes it straight to the engine (ConfigParser interpolation chokes on the
percent-encoded socket path). Migrations run as a Cloud Run Job with the new image **before** the service revision is
deployed, while the previous revision is still serving. Hence the rule: every migration must be backward compatible
with the previous code (new columns nullable or with defaults, drops in two PRs). CI applies migrations to a fresh
Postgres and runs `alembic check` so a model change without a migration fails the build. Full rules in
`.claude/rules/database.md`, workflow in the `/migration` skill.

## 6. Frontend

React 19, TypeScript, Vite 8, `react-router-dom`, `@tanstack/react-query`, Tailwind CSS v4 via the Vite plugin.

**Data flow.** Components never call `fetch`. `src/api/client.ts` wraps `fetch`, prefixes the relative `/api` path and
turns FastAPI's `{"detail": ...}` into an `ApiError` message. `src/api/schema.d.ts` is generated from the backend
OpenAPI document by `make types` (openapi-typescript); `src/api/recipes.ts` aliases those types and holds the request
functions. The `contract` CI job fails when the generated file is stale, so the API contract cannot drift silently. `src/hooks/useRecipes.ts` exposes `useCreateRecipe`
(mutation; seeds the detail cache on success) and `useRecipe(id)` (query with `AbortSignal`, `staleTime: Infinity`).

**UI.** `HomePage`: hero, chip-style `ProductInput` (Enter or comma adds, Backspace removes, suggestion chips,
30-item cap), servings toggle, optional preferences, submit with pending / error states, then `RecipeCard`.
`RecipeCard`: title, description, time, servings, ingredients with "докупити" badges, numbered steps, tip, and the
model's clarifying question when present. `RecipePage` (`/recipes/:id`) is lazy-loaded and renders a stored recipe.

**Styling.** Tailwind only; the single stylesheet `src/index.css` defines `@theme` tokens taken from the Canva deck
(olive background, dark green text, cream cards, orange accent, Fraunces display font). `prettier-plugin-tailwindcss`
sorts classes. Mobile-first; all interactive elements have focus rings; pending uses `aria-busy`/`role="status"`,
errors `role="alert"`.

**Quality gates.** `oxlint`, `prettier --check`, `tsc -b && vite build`.

## 7. Infrastructure and delivery

**Google Cloud project** `shashlychky`, region `europe-central2` (Warsaw).

| Component | Resource |
|---|---|
| backend | Cloud Run service `shashlychky-backend`, `--port 8080`, 0–3 instances, Cloud SQL attached, secrets mounted as env |
| migrations | Cloud Run Job `shashlychky-migrate`, same image, command `alembic upgrade head` |
| images | Artifact Registry repo `shashlychky` |
| frontend | Firebase Hosting site `shashlychky`, rewrite `/api/**` → Cloud Run service |
| database | Cloud SQL Postgres 18 instance `shashlychky`, database `shashlychky` |
| secrets | Secret Manager `db-password`, `gemini-api-key`; runtime SA has `secretAccessor` + `cloudsql.client` |
| deploy identity | service account `deploy-sa` with Cloud Run admin, Artifact Registry writer, Firebase Hosting admin |
| GitHub auth | Workload Identity Federation pool `github`, restricted to repo `NastiaVeret/shashlychky`; no JSON keys anywhere |

**GitHub Actions.**

- `ci.yml` on every PR and push to `main`: backend lint/typecheck/migrations/`alembic check`/tests against a Postgres
  service container; frontend lint/format/build; `contract` job regenerating the TS types and diffing them.
- `deploy.yml` on push to `main`: build and push the backend image → deploy and execute the migration job → deploy
  the Cloud Run service → build the frontend and deploy to Firebase Hosting (after the backend, because Firebase
  validates the rewrite target). Configuration comes from repository variables (`GCP_PROJECT_ID`, `GCP_REGION`,
  `GCP_ARTIFACT_REPO`, `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `CLOUDSQL_INSTANCE`).
- `preview.yml` on PRs touching `frontend/`: deploys a 7-day Firebase preview channel and comments the URL on the PR.

A merge into `main` is a production deploy; the README has the one-time GCP setup commands.

## 8. Team workflow and Claude Code setup

Everything a teammate's Claude Code needs lives in the repo:

- `CLAUDE.md`: commands, language policy (code and docs in English, UI text in Ukrainian), architecture decisions,
  workflow, and what not to do without discussion.
- `.claude/rules/`: `backend.md`, `frontend.md`, `database.md` load only when touching those paths; `git.md` always
  (branches, Conventional Commits, PR rules, no force push).
- `.claude/skills/`: `/check` (all quality gates), `/new-endpoint`, `/new-page`, `/migration`, `/pr`, plus the
  idiom guides `python-best-practices`, `react-best-practices` and `tailwind` that load automatically when relevant.
- `.claude/agents/`: `reviewer` (read-only review against the project rules), `test-writer`,
  `frontend-integrator` (derives TS types, request functions and hooks from the backend OpenAPI schema).
- `.claude/settings.json`: allowlist for safe commands, deny-list for `.env` and keys, and a `PostToolUse` hook that
  runs `ruff` / `prettier` on every file Claude edits.
- `.github/pull_request_template.md`: checklist incl. API-contract and migration impact.
- `Makefile`: one entry point (`make install|dev|check|migration|types|seed`); `.pre-commit-config.yaml`: local hooks
  for every developer; `.github/dependabot.yml`: weekly grouped dependency PRs.

## 9. Decisions worth knowing (short ADRs)

| Decision | Why | Alternative considered |
|---|---|---|
| Monorepo | one PR can change API + UI + migration together; one CI | two repos |
| Firebase Hosting for the frontend | free CDN + SSL, same-origin `/api` rewrite removes CORS and backend URL config | nginx container on Cloud Run (first version, replaced) |
| Cloud Run Job for migrations | same image as the service, runs before the new revision, fails the deploy on error | running Alembic from the GitHub runner through Cloud SQL Auth Proxy |
| Workload Identity Federation | no long-lived keys in GitHub | service-account JSON key secret |
| psycopg v3 | one driver for async app and sync Alembic | asyncpg + psycopg2 |
| JSONB `content` column | recipe shape will evolve with the prompt; validated by Pydantic on read/write | normalised ingredients/steps tables |
| Gemini Developer API with API key | free tier, simplest for a student project; key stays server-side | Vertex AI with the runtime service account (no key; revisit if quotas or data-residency matter) |
| `gemini-3.1-flash-lite` + fallback | cheapest open model; fallback absorbs its intermittent 503/504 | single model with same-model retries (slower recovery) |
| Tailwind v4, CSS-first config | tokens from the Canva design in one place, no CSS files to review | CSS modules |
| Generated TS types from OpenAPI | backend schemas are the only source of truth; CI catches drift | hand-mirrored interfaces (first version) |
| `openapi-typescript` via pinned `npx`, not in package.json | it peers on TypeScript 5 while the app is on 6; it is a codegen tool, not a runtime dependency | `legacy-peer-deps` for the whole project |

## 10. Known limitations and next steps

- Accounts exist (email + password, see "Authentication" in section 3), but no profiles or dietary
  restrictions yet. No password reset and no email confirmation: both need an email provider.
- No rate limiting on `POST /recipes`; the only guard is input size. Add per-IP limits before public promotion.
- No eval set for recipe quality; the deck plans 50–100 reference recipes in CI.
- Cold starts: `min-instances=0` saves money but adds a few seconds to the first request after idle.
- The Gemini key and the DB password were handled in a chat session during setup; rotate both at a convenient time
  (`gcloud sql users set-password`, new secret versions). No code changes are needed.
- `shashlychky-c19a8` is an accidental empty Firebase project; delete it in the console.
