.PHONY: setup data test test-backend test-frontend lint lint-backend lint-frontend format dev

BACKEND := uv run --directory backend
FRONTEND := npm --prefix frontend

# StatsBomb competition and season; default is the FIFA World Cup 2022.
COMPETITION ?= 43
SEASON ?= 106

setup:
	uv sync --directory backend
	$(FRONTEND) ci
	$(BACKEND) pre-commit install

data:
	$(BACKEND) python -m pitchquery.data.build --competition $(COMPETITION) --season $(SEASON)

test: test-backend test-frontend

test-backend:
	$(BACKEND) pytest

test-frontend:
	$(FRONTEND) test

lint: lint-backend lint-frontend

lint-backend:
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(BACKEND) mypy

lint-frontend:
	$(FRONTEND) run typecheck
	$(FRONTEND) run lint

format:
	$(BACKEND) ruff check --fix .
	$(BACKEND) ruff format .
	$(FRONTEND) run format

dev:
	$(FRONTEND) run dev
