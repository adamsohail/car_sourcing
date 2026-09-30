.PHONY: install lint test check serve run smoke

install:
	uv sync && uv run pre-commit install --hook-type pre-commit --hook-type pre-push

lint:
	uv run ruff check . && uv run ruff format --check . && uv run mypy src

test:
	uv run pytest --cov

check: lint test

serve:
	uv run car-sourcing serve --port 8080

run:
	uv run car-sourcing run

smoke:
	uv run car-sourcing smoke
