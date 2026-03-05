# TBD Platform — Developer Makefile
#
# Common tasks for local development. Run `make help` to see available targets.

.DEFAULT_GOAL := help
.PHONY: help up down restart logs api-logs web-logs \
        lint lint-api lint-web test test-api \
        migrate migrate-new db-backup db-restore \
        fmt fmt-api clean

# ---------------------------------------------------------------------------
# Infrastructure
# ---------------------------------------------------------------------------

up: ## Start all services (docker-compose)
	docker compose -f infra/docker-compose.yml up -d

up-dev: ## Start dev services (with hot-reload volumes)
	docker compose -f infra/docker-compose.dev.yml up -d

down: ## Stop all services
	docker compose -f infra/docker-compose.yml down

restart: ## Restart all services
	docker compose -f infra/docker-compose.yml restart

logs: ## Tail all service logs
	docker compose -f infra/docker-compose.yml logs -f --tail=100

api-logs: ## Tail API logs
	docker compose -f infra/docker-compose.yml logs -f --tail=100 api

web-logs: ## Tail Web UI logs
	docker compose -f infra/docker-compose.yml logs -f --tail=100 web

# ---------------------------------------------------------------------------
# Linting & Formatting
# ---------------------------------------------------------------------------

lint: lint-api lint-web ## Run all linters

lint-api: ## Lint API (ruff)
	cd api && ruff check . && ruff format --check .

lint-web: ## Lint Web UI (eslint + tsc)
	cd web && npm run lint && npx tsc --noEmit

fmt: fmt-api ## Auto-format all code

fmt-api: ## Auto-format API code (ruff)
	cd api && ruff check --fix . && ruff format .

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

test: test-api ## Run all tests

test-api: ## Run API tests (pytest)
	cd api && SECRET_KEY=test-secret-key-long-enough-32chars pytest -v --tb=short

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

migrate: ## Run Alembic migrations to head
	cd api && alembic upgrade head

migrate-new: ## Create a new Alembic migration (usage: make migrate-new MSG="add foo table")
	cd api && alembic revision --autogenerate -m "$(MSG)"

db-backup: ## Run PostgreSQL backup
	bash infra/backup/pg-backup.sh

db-restore: ## Restore PostgreSQL from backup (usage: make db-restore FILE=path/to/dump.sql.gz)
	bash infra/backup/pg-restore.sh $(FILE)

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

clean: ## Remove Python caches, node_modules build artifacts
	find api -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find api -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf web/.next web/node_modules/.cache

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'
