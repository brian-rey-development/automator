# Automator - tareas de desarrollo.
# Uso: `make <target>`. `make help` lista todo.

VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
BIN := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help install dev run samples demo icon lock lint format format-check typecheck test cov import-lint file-size check build clean

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Crea el entorno virtual e instala todo (app + dev)
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

dev: install ## Alias de install para preparar el entorno de desarrollo

run: ## Ejecuta la aplicacion desde el codigo fuente
	$(PY) -m automator

samples: ## Genera facturas de ejemplo en la carpeta de entrada configurada
	$(PY) scripts/generate_sample_invoices.py

demo: samples run ## Genera facturas de ejemplo y abre la app para probarla

icon: ## Genera el icono de marca (assets/automator.ico y .png)
	$(PY) scripts/generate_icon.py

lock: ## Regenera el lockfile de dependencias (requiere uv)
	uv lock

lint: ## Linting con ruff (sin modificar archivos)
	$(BIN)/ruff check .

format: ## Formatea y ordena imports con ruff
	$(BIN)/ruff format .
	$(BIN)/ruff check . --fix

format-check: ## Verifica el formato sin modificar archivos
	$(BIN)/ruff format --check .

typecheck: ## Chequeo de tipos estricto con mypy
	$(BIN)/mypy

test: ## Ejecuta la bateria de tests
	$(BIN)/pytest

cov: ## Ejecuta los tests con reporte de cobertura
	$(BIN)/pytest --cov

import-lint: ## Enforcea ui -> services -> domain
	PYTHONPATH=src $(BIN)/lint-imports

file-size: ## Falla si un modulo de produccion supera 200 lineas
	$(PY) scripts/check_file_size.py

check: lint format-check typecheck cov import-lint file-size ## Corre linting, tipos, tests con cobertura y contratos

build: icon ## Genera el ejecutable con PyInstaller (genera el icono primero)
	$(BIN)/pyinstaller automator.spec --noconfirm --clean

clean: ## Borra artefactos de build, cache y cobertura
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
