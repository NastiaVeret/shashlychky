# Git and PRs

## Branches

`feat/<short>`, `fix/<short>`, `chore/<short>`, `docs/<short>`. Branch from `main`, lowercase, hyphen-separated.

## Commits

Conventional Commits, subject up to 72 characters, imperative mood:

```
feat(backend): add orders endpoint
fix(frontend): handle 404 on order page
chore(ci): bump setup-uv to v6
```

Scopes: `backend`, `frontend`, `ci`, `deps`, `docs`. One commit = one logical change.
Never commit: `.env`, GCP keys, `node_modules`, `.venv`, build artifacts.

## PRs

- Use the template in `.github/pull_request_template.md`; fill in every section.
- Keep PRs small: up to ~400 lines of diff. Split anything bigger.
- CI must be green before requesting review.
- Squash merge; the squash commit message follows Conventional Commits.
- Merging into `main` deploys to production. Make sure the change is ready.

## Claude Code and git

- Commit and push only when a human explicitly asks.
- Never `git push --force` to `main` or shared branches.
- Do not rewrite history (`rebase`, `amend`) of pushed commits unless asked.
