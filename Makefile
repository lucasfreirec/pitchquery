.PHONY: setup test test-backend test-frontend lint lint-backend lint-frontend format dev

BACKEND := uv run --directory backend
FRONTEND := npm --prefix frontend

setup:
	uv sync --directory backend
	$(FRONTEND) ci
	$(BACKEND) pre-commit install

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
