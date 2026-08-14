# Guia de contribucion

## Entorno

```bash
make install          # crea .venv e instala app + dependencias de desarrollo
pre-commit install    # instala los hooks de calidad (opcional pero recomendado)
```

Requiere Python 3.11+.

Para una instalacion reproducible bit a bit hay un lockfile (`uv.lock`): con
[uv](https://docs.astral.sh/uv/), `uv sync --extra dev` instala exactamente las
mismas versiones. Regenerar el lock con `make lock` cuando cambian las dependencias.

## Flujo de trabajo

1. Crear una rama a partir de `main`.
2. Escribir el codigo y sus tests.
3. `make check` en verde (lint + tipos + tests) antes de commitear.
4. Commits en ingles, formato Conventional Commits.
5. Abrir un PR; la CI corre lint, formato, tipos y tests en Python 3.11/3.12/3.13.

## Estandares de codigo

- **Identificadores en ingles, comentarios en español.** Comentar solo el porque
  no obvio (una invariante, un workaround), nunca lo que el codigo ya dice.
- Tipado estricto (`mypy --strict`), sin `Any` injustificado.
- Funciones cortas (<= 20 lineas), retornos tempranos, inmutabilidad por defecto.
- Sin em dashes en ningun texto (codigo, docs, commits).
- Validar en los bordes (input de usuario, APIs externas); confiar en el interior.
- Nada de datos reales (nombres de empresa, CUIT) en el codigo ni en los tests:
  usar datos ficticios genericos.

## Donde va cada cosa

- Logica de negocio pura -> `domain/` (con tests).
- IO, hilos, orquestacion -> `services/`.
- Interfaz -> `ui/` (sin reglas de negocio).

Antes de agregar una regla de clasificacion, preguntarse: ante la duda, ¿la
factura va a revision? El principio es **nunca archivar mal en silencio**.

## Herramientas

```bash
ruff check .      # linting
ruff format .     # formateo
mypy              # tipos estrictos
pytest            # tests
pytest --cov      # tests con cobertura
```

Todo esta configurado en `pyproject.toml`. La CI usa exactamente los mismos
comandos.

## Tests

- El nucleo (`domain/`, `services/`) debe tener tests que cubran cada rama de
  decision (movido, sin clasificar, duplicado, revision, cuarentena).
- La UI se testea con smokes funcionales en `tests/test_ui.py`, que se saltean
  solos si no hay display (en CI corren bajo xvfb).
- La cobertura del nucleo tiene un piso del 80% (`fail_under` en `pyproject.toml`);
  la CI falla si baja de ahi.
- Los fixtures de ejemplo estan en `tests/conftest.py`. Nunca usar datos reales.

## Commits

Formato Conventional Commits, en ingles:

```
feat(services): add duplicate detection to the processor
fix(config): keep user config on transient read errors
docs: document the folder template tokens
```
