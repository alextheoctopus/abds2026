
.RECIPEPREFIX := >

.DEFAULT_GOAL := run

COMPOSE = docker compose --env-file .env.local
include .env.local

.PHONY: run stop check-running schema gen load setup teardown services clean

# Builds Docker images.
build:
>$(COMPOSE) build

# Starts all services.
run:
>$(COMPOSE) up -d

# Rebuilds and restarts services.
rebuild:
>$(COMPOSE) up -d --build

# Shows all service statuses.
services:
>$(COMPOSE) ps

# Stops all running services.
stop:
>$(COMPOSE) down

# Stops containers and Docker-managed volumes.
clean:
>$(COMPOSE) down -v

# Checks ClickHouse availability.

check-running:
>@$(COMPOSE) exec -T clickhouse clickhouse-client --user "$(CLICKHOUSE_USER)" --password "$(CLICKHOUSE_PASSWORD)" --query "SELECT 1" || (echo ERROR: ClickHouse is unavailable. Run make run first. & exit /b 1)

# Removes tables and data.
teardown: check-running
>python scripts/run_sql.py sql/teardown.sql

# Creates the star schema.
schema: check-running
>@echo "Creating tables..."
>python scripts/run_sql.py sql/01_create_star.sql

# Generates datasets.
gen:
>python scripts/generate_data.py

# Loads datasets.
load: check-running
>@echo "Loading datasets..."
>python scripts/load_data.py

# Creates schema, generates and loads data.
setup: check-running
>$(MAKE) schema
>$(MAKE) gen
>$(MAKE) load
