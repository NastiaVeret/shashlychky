---
name: pr
description: Prepare changes for a pull request - run all checks, propose a Conventional Commits message, create the PR with gh using the project template. Use when the user says "make a PR", "prepare for merge", "commit and open a PR".
disable-model-invocation: true
allowed-tools: Bash(git *), Bash(gh *), Bash(cd *), Bash(uv run *), Bash(npm run *)
---

# Prepare a PR

## 1. State

```bash
git status --short && git branch --show-current && git log --oneline main..HEAD
```

If the current branch is `main`: stop and propose a branch name (`feat/...`, `fix/...`) based on the changes. Create it only after the user agrees.

## 2. Checks

Run the `/check` skill. If anything is red, fix it or stop and ask. Never open a PR with red checks.

## 3. Commit

Review `git diff` (staged + unstaged). Propose a Conventional Commits message
(`type(scope): summary`, scope from `backend|frontend|ci|deps|docs`). Show it to the user and commit **only after confirmation**.
Never stage `.env`, keys, or build artifacts.

## 4. PR

```bash
git push -u origin "$(git branch --show-current)"
gh pr create --title "<same subject as the commit>" --body-file <temp file based on the template>
```

Fill the body using `.github/pull_request_template.md`: what and why, how it was verified, whether the API contract or
migrations changed, whether new Cloud Run environment variables are needed. With several commits, the title summarizes them.

## 5. Report

The PR link and one sentence on what was sent for review. Remind that merging into `main` deploys to production.
