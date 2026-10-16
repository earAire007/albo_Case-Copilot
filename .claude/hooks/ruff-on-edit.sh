#!/usr/bin/env bash
# PostToolUse (Edit|Write): ruff only on the edited file, if it is Python.
# Exit 2 sends stderr back to the agent as feedback (spec 01b).
set -uo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
file="$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')"

[[ "$file" == *.py && -f "$file" ]] || exit 0

if ! out="$(cd "$repo" && uv run --quiet ruff check "$file" 2>&1 && uv run --quiet ruff format --check "$file" 2>&1)"; then
  printf 'ruff falló en %s:\n%s\n' "$file" "$out" >&2
  exit 2
fi
exit 0
