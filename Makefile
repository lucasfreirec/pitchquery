.PHONY: setup data bench test test-backend test-frontend lint lint-backend lint-frontend format dev dev-backend dev-frontend up down

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

bench:
	$(BACKEND) python benchmarks/bench.py

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

# API on :8000 and the Vite dev server on :5173, together. Ctrl-C stops both.
dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(BACKEND) uvicorn pitchquery.api:app --reload --port 8000

dev-frontend:
	$(FRONTEND) run dev

# Everything in Docker: app on http://localhost:8080 (first start builds the data).
up:
	docker compose up --build

down:
	docker compose down
