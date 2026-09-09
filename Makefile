# llm-port developer tasks.
# Every target runs inside a project-local virtualenv at $(VENV).

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

PYTHON ?= python3.12
VENV   ?= .venv
BIN    := $(VENV)/bin
PY     := $(BIN)/python
PIP    := $(BIN)/pip

# Marker file: lets `make test` re-create the venv only when dependencies move.
STAMP := $(VENV)/.install-stamp

.DEFAULT_GOAL := help
.PHONY: help setup test integration-test lint format typecheck check build cleanup

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

$(STAMP): pyproject.toml
	@test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e '.[dev]'
	@touch $(STAMP)

setup: $(STAMP) ## Create the development virtualenv and install llm-port in editable mode
	@echo "Environment ready. Activate with: source $(BIN)/activate"

test: $(STAMP) ## Run the offline unit test suite
	$(BIN)/pytest tests/unit -m 'not integration' --cov=llm_port

integration-test: $(STAMP) ## Run live provider tests (requires provider credentials)
	$(BIN)/pytest tests/integration -m integration -ra

lint: $(STAMP) ## Check formatting and lint rules
	$(BIN)/ruff check src tests
	$(BIN)/ruff format --check src tests

format: $(STAMP) ## Apply formatting and autofixable lint rules
	$(BIN)/ruff format src tests
	$(BIN)/ruff check --fix src tests

typecheck: $(STAMP) ## Run mypy in strict mode
	$(BIN)/mypy

check: lint typecheck test ## Run everything CI runs

build: $(STAMP) ## Build the sdist and wheel into dist/
	rm -rf dist
	$(PY) -m build

cleanup: ## Remove the virtualenv, build output, and caches
	rm -rf $(VENV) dist build .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type d -name '*.egg-info' -prune -exec rm -rf {} +
