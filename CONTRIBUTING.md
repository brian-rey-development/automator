# Contribution guide

## Environment

```bash
make install          # creates .venv and installs app + dev dependencies
pre-commit install    # installs the quality hooks (optional but recommended)
```

Requires Python 3.11+.

For a bit-for-bit reproducible install there is a lockfile (`uv.lock`): with
[uv](https://docs.astral.sh/uv/), `uv sync --extra dev` installs exactly the
same versions. Regenerate the lock with `make lock` when dependencies change.

## Workflow

1. Create a branch from `main`.
2. Write the code and its tests.
3. `make check` green (lint + format + types + tests with coverage +
   import-linter + file size) before committing.
4. Commits in English, Conventional Commits format.
5. Open a PR; CI runs the same checks on Python 3.11, 3.12 and 3.13, and a
   Windows job builds the executable.

## Code standards

- **Identifiers and comments in English.** Comment only the non-obvious why (an
  invariant, a workaround). User-facing strings (UI labels, dialog messages,
  notifications) stay in Spanish for the end users.
- Strict typing (`mypy --strict`), no unjustified `Any`.
- Short functions (<= 20 lines), early returns, immutability by default.
- Production modules stay at or under 200 lines (`scripts/check_file_size.py`,
  part of `make check` and CI).
- No em dashes in any text (code, docs, commits). Use a regular hyphen, a comma,
  or restructure the sentence.
- Validate at the boundaries (user input, external APIs); trust the interior.
- Use generic fictional data in the code and the tests (company names, CUITs).

## Where things go

- Pure business logic -> `domain/` (with tests). Filing policy lives in
  `domain/filing/decide_filing`.
- IO, threads, orchestration -> `services/`.
- Interface -> `ui/`. Shell composes views. Controllers own IO. Widgets stay
  away from SQLite.
- Validated frozen config -> `config/`.

Import-linter enforces `ui -> services -> domain`. Domain does not import
config. Config does not import services.

Before adding a classification rule, ask yourself: when in doubt, does the
invoice go to review? The principle is **No invoice is ever misfiled or lost
silently.** Fuzzy buyer matching is `NEEDS_REVIEW` and lands in `_PARA_REVISAR`.

## Tools

```bash
ruff check .      # linting
ruff format .     # formatting
mypy              # strict types
pytest            # tests
pytest --cov      # tests with coverage (fail_under 90)
```

`make check` also runs `PYTHONPATH=src lint-imports` and
`python scripts/check_file_size.py`. Everything is configured in
`pyproject.toml`. CI uses the same commands.

## Tests

- Tests live under `tests/{domain,services,ui,config}/`, mirroring the layers.
- The core (`domain/`, `services/`) must cover each decision branch (moved,
  unclassified, duplicate, review, quarantine).
- UI smokes live in `tests/ui/` (for example `test_main_window.py`). They skip
  themselves if `CTk()` fails to open a display; in CI they run under xvfb.
- Core coverage has a floor of 90% (`fail_under` in `pyproject.toml`). The UI
  package is omitted (`omit = ["*/ui/*"]`).
- Shared fixtures are in `tests/conftest.py`. Sample invoice texts live in
  `tests/fixtures/invoices.py`.

## Commits

Conventional Commits format, in English:

```
feat(services): add duplicate detection to the processor
fix(config): keep user config on transient read errors
docs: document the folder template tokens
```
