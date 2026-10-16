.PHONY: test lint check-docs dataset mock

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
