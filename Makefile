.PHONY: check test lint check-docs dataset mock mcp smoke api

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
