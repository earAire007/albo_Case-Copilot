#!/usr/bin/env bash
# Stop: full lint + tests before the agent ends its turn (spec 01b).
# Exit 2 blocks the stop and sends the failure to the agent. If this hook already
# blocked once in this cycle (stop_hook_active), report but let it stop: no loops.
set -uo pipefail

repo="$(cd "$(dirname "$0")/../.." && pwd)"
active="$(python3 -c 'import json, sys; print(str(json.load(sys.stdin).get("stop_hook_active", False)).lower())')"
cmd="${VERIFY_ON_STOP_CMD:-make lint && make test}"

if out="$(cd "$repo" && bash -c "$cmd" 2>&1)"; then
  exit 0
fi

summary="$(printf '%s\n' "$out" | tail -n 40)"
if [[ "$active" == "true" ]]; then
  printf 'verify-on-stop: sigue fallando tras un reintento; revisión humana necesaria.\n%s\n' "$summary" >&2
  exit 0
fi
printf 'verify-on-stop: `%s` falló. Corrige antes de terminar:\n%s\n' "$cmd" "$summary" >&2
exit 2
