#!/usr/bin/env bash
# commit-msg hook: enforce Conventional Commits (see .claude/rules/git.md).
# Usage: check-commit-msg.sh <path-to-commit-message-file>
set -euo pipefail
subject=$(grep -v '^#' "$1" | sed -n '1p')
pattern='^(feat|fix|chore|docs|refactor|test|perf|ci|build|style|revert)(\([a-z0-9-]+\))?!?: .{1,72}$'
if [[ "$subject" =~ ^(Merge|Revert|fixup!|squash!) ]]; then exit 0; fi
if ! [[ "$subject" =~ $pattern ]]; then
  echo "✖ commit subject must follow Conventional Commits, e.g.:"
  echo "    feat(backend): add orders endpoint"
  echo "  got: $subject"
  exit 1
fi
