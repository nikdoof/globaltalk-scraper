.PHONY: lint format test clean

lint:
	uv run ruff check

test:
	uv run pytest tests/ -v

format:
	uv run ruff format

clean:
	rm -rf dist/ build/ .ruff_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name '*.egg-info' -exec rm -rf {} +
