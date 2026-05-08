.PHONY: install test lint fmt up down migrate backfill rank replay monitor paper

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

fmt:
	ruff check --fix src tests

up:
	docker compose up -d postgres
	@echo "postgres up; run \`make migrate\` next"

down:
	docker compose down

migrate:
	alembic upgrade head

backfill:
	copytrader backfill

rank:
	copytrader rank --window 30 --watchlist-top 10

replay:
	copytrader replay --window 30 --delays 30,60,120

monitor:
	copytrader monitor

paper:
	copytrader paper --copy-usd 5
