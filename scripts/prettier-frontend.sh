#!/usr/bin/env bash
# pre-commit wrapper: pre-commit passes paths relative to the repo root, while prettier must run
# inside frontend/ so that prettier-plugin-tailwindcss resolves from frontend/node_modules.
set -euo pipefail
cd "$(dirname "$0")/../frontend"
files=("${@#frontend/}")
exec node_modules/.bin/prettier --write --log-level warn "${files[@]}"
