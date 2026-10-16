.PHONY: check test lint check-docs dataset mock

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
