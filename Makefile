.PHONY: check test lint check-docs dataset mock mcp smoke api console console-check evals evals-label-template evals-label-template-r2 evals-judge evals-judge-round2 evals-render up

# Run before every commit: Claude Code hooks don't run outside that tool.
check:
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) check-docs

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run pyright
	uv run lint-imports

check-docs:
	uv run python scripts/check_docs.py

dataset:
	uv run python data/generate.py --out data

mock:
	uv run uvicorn backend.mock_core.api:app --reload --port 8000

mcp:
	uv run python -m mcp_server --customer-id $(CUSTOMER)

# Real model, costs money, not deterministic: outside `make check`.
smoke:
	PYTHONPATH=. uv run $(if $(wildcard .env),--env-file .env,) python scripts/smoke.py

# Copilot API + in-process worker (real model: needs credentials).
api:
	PYTHONPATH=. uv run $(if $(wildcard .env),--env-file .env,) uvicorn backend.app.api:_production_app --factory --port 8001

# Operations console (spec 07). Needs Node; outside `make check` so Python stays Node-free.
console-check:
	cd console && npm ci --no-audit --no-fund && npx tsc --noEmit && npx vitest run && npx vite build

# Dev server on :5173, proxies /api to `make api` on :8001.
console:
	cd console && npm run dev

# Spec 08. Real model, costs money: outside `make check`. MAX_USD is mandatory.
# (A literal comma inside $(or ...) splits arguments: keep the list in a variable.)
DEFAULT_VARIANTS := opus-5.5,sonnet-5.5
evals:
	PYTHONPATH=. uv run $(if $(wildcard .env),--env-file .env,) python -m evals.runner --variant $(or $(VARIANT),$(DEFAULT_VARIANTS)) $(if $(MAX_USD),--max-usd $(MAX_USD),) $(if $(CASES),--cases $(CASES),)

# ~10 anonymous answers from the latest run for a person to label (never overwrites labels).
evals-label-template:
	PYTHONPATH=. uv run python -m evals.runner --label-template --round 1 $(if $(LABEL_CASES),--label-cases $(LABEL_CASES),)

evals-label-template-r2:
	PYTHONPATH=. uv run python -m evals.runner --label-template --round 2

# Blind judge over the labeled answers; agreement per variant into EVALS.md. Costs money:
# MAX_USD is mandatory here too.
evals-judge:
	PYTHONPATH=. uv run $(if $(wildcard .env),--env-file .env,) python -m evals.runner --judge $(if $(MAX_USD),--max-usd $(MAX_USD),)

evals-judge-round2:
	PYTHONPATH=. uv run $(if $(wildcard .env),--env-file .env,) python -m evals.runner --judge --round 2 $(if $(MAX_USD),--max-usd $(MAX_USD),)

evals-render:
	@test -n "$(RUN_ID)" || (echo "RUN_ID es obligatorio: indica el id de la corrida guardada." >&2; exit 2)
	PYTHONPATH=. uv run python -m evals.runner --render-run $(RUN_ID)

up:
	docker compose up --build
