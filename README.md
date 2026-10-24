# Shashlychky

Monorepo: FastAPI backend on Google Cloud Run + React frontend on Firebase Hosting, deployed via GitHub Actions.

```
backend/    FastAPI (Python 3.13, uv)
frontend/   React 19 + TypeScript + Vite
.github/    CI (lint, tests, build), deployment, PR preview channels
.claude/    shared Claude Code configuration (rules, skills, agents, hooks)
```

## Local development

Backend (http://localhost:8000, Swagger at /docs):

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn app.main:app --reload
```

Frontend (http://localhost:5173, `/api` requests are proxied to the backend):

```bash
cd frontend
npm install
npm run dev
```

Backend in Docker (as in Cloud Run): `docker compose up --build`, then http://localhost:8000.
The frontend is static; locally always run it with `npm run dev`.

## Checks

```bash
# backend
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest
# frontend
cd frontend && npm run lint && npm run format:check && npm run build
```

## Deployment

| Part | Where | How |
|---|---|---|
| Backend | Cloud Run service `shashlychky-backend` | Docker image pushed to Artifact Registry |
| Frontend | Firebase Hosting (`https://PROJECT_ID.web.app`) | Static `dist/` upload; `/api/**` is rewritten to the Cloud Run backend, so frontend and API share one origin and no CORS is needed |

Workflows:

- `.github/workflows/ci.yml`: lint, typecheck, tests, build on every PR and push to `main`.
- `.github/workflows/deploy.yml`: on push to `main`, deploys the backend, then the frontend (Firebase validates the Cloud Run rewrite target, so order matters).
- `.github/workflows/preview.yml`: on every PR that touches `frontend/`, deploys a 7-day Firebase preview channel and comments the URL on the PR.

### One-time GCP / Firebase setup

Replace `PROJECT_ID`, `REGION`, `GITHUB_ORG/REPO`:

```bash
gcloud config set project PROJECT_ID
gcloud services enable run.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com \
  firebase.googleapis.com firebasehosting.googleapis.com

# Add Firebase to the project and create the Hosting site (one-off, needs Firebase CLI: npm i -g firebase-tools)
firebase login
firebase projects:addfirebase PROJECT_ID
firebase hosting:sites:create PROJECT_ID --project PROJECT_ID   # site id = project id → https://PROJECT_ID.web.app

# Artifact Registry
gcloud artifacts repositories create shashlychky --repository-format=docker --location=REGION

# Deployment service account
gcloud iam service-accounts create deploy-sa
for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser \
            roles/firebasehosting.admin roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding PROJECT_ID \
    --member="serviceAccount:deploy-sa@PROJECT_ID.iam.gserviceaccount.com" --role="$role"
done

# Workload Identity Federation for GitHub
gcloud iam workload-identity-pools create github --location=global
gcloud iam workload-identity-pools providers create-oidc github \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='GITHUB_ORG/REPO'"
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding deploy-sa@PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github/attribute.repository/GITHUB_ORG/REPO"
```

Then in GitHub → Settings → Secrets and variables → Actions → Variables:

| Variable | Value |
|---|---|
| `GCP_PROJECT_ID` | project id (also the Firebase project and Hosting site id) |
| `GCP_REGION` | Cloud Run region, e.g. `europe-central2` (the workflow writes it into `firebase.json`) |
| `GCP_ARTIFACT_REPO` | `shashlychky` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/github/providers/github` |
| `GCP_SERVICE_ACCOUNT` | `deploy-sa@PROJECT_ID.iam.gserviceaccount.com` |

Optional secret `BACKEND_ENV_VARS` (`KEY=value,KEY2=value2`) for backend environment variables.

### Manual frontend deploy from a laptop

```bash
cd frontend && npm run build && npx firebase-tools deploy --only hosting --project PROJECT_ID
```

### Custom domain

Firebase console → Hosting → Add custom domain. SSL is issued automatically. The `/api/**` rewrite keeps working on the custom domain.

## Working with Claude Code

The shared configuration lives in the repo and works the same for everyone:

| What | Where | Purpose |
|---|---|---|
| Project context | `CLAUDE.md` | Commands, style, architecture decisions, workflow |
| Per-area rules | `.claude/rules/` | `backend.md` and `frontend.md` load only when touching those folders, `git.md` always |
| Skills | `.claude/skills/` | `/check` all checks, `/new-endpoint` endpoint by convention, `/new-page` React page, `/pr` commit and PR |
| Agents | `.claude/agents/` | `reviewer` reviews a diff without changing code, `test-writer` writes tests by the project reference, `frontend-integrator` wires the frontend to the backend API (types, request functions, hooks, pages) |
| Settings | `.claude/settings.json` | Allowlist for safe commands, deny reading `.env`, auto-format hook after every edit |

Personal settings go to `.claude/settings.local.json` (gitignored).
New rules and skills are added via PR, like code.
