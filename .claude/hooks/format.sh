#!/usr/bin/env bash
# PostToolUse hook: auto-formats the file Claude just changed via Edit/Write.
# Reads the tool JSON from stdin, extracts tool_input.file_path, runs ruff or prettier.
set -euo pipefail

FILE=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null || true)
[ -n "$FILE" ] && [ -f "$FILE" ] || exit 0

ROOT=$(cd "$(dirname "$0")/../.." && pwd)

case "$FILE" in
  "$ROOT"/backend/*.py)
    cd "$ROOT/backend" && uv run --quiet ruff format --quiet "$FILE" >/dev/null 2>&1 || true
    cd "$ROOT/backend" && uv run --quiet ruff check --fix --quiet "$FILE" >/dev/null 2>&1 || true
    ;;
  "$ROOT"/frontend/*.ts|"$ROOT"/frontend/*.tsx|"$ROOT"/frontend/*.css)
    cd "$ROOT/frontend" && npx --no-install prettier --write --log-level silent "$FILE" >/dev/null 2>&1 || true
    ;;
esac
exit 0
