.PHONY: install test lint fmt up down migrate web indexer worker

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

fmt:
	ruff check --fix src tests

up:
	docker compose up -d

down:
	docker compose down

migrate:
	alembic upgrade head

web:
	python -m copytrader.runtime.web_main

indexer:
	python -m copytrader.runtime.indexer_main

worker:
	python -m copytrader.runtime.worker_main
