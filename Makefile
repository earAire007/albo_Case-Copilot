.PHONY: test lint dataset mock

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run ruff format --check .

dataset:
	uv run python data/generate.py --out data

mock:
	uv run uvicorn backend.mock_core.api:app --reload --port 8000
