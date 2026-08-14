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
3. `make check` green (lint + types + tests) before committing.
4. Commits in English, Conventional Commits format.
5. Open a PR; CI runs lint, formatting, types and tests on Python 3.11/3.12/3.13.

## Code standards

- **Identifiers and comments in English.** Comment only the non-obvious why (an
  invariant, a workaround), never what the code already says. User-facing strings
  (UI labels, dialog messages, notifications) stay in Spanish for the end users.
- Strict typing (`mypy --strict`), no unjustified `Any`.
- Short functions (<= 20 lines), early returns, immutability by default.
- No em dashes in any text (code, docs, commits).
- Validate at the boundaries (user input, external APIs); trust the interior.
- No real data (company names, CUITs) in the code or the tests: use generic
  fictional data.

## Where things go

- Pure business logic -> `domain/` (with tests).
- IO, threads, orchestration -> `services/`.
- Interface -> `ui/` (no business rules).

Before adding a classification rule, ask yourself: when in doubt, does the
invoice go to review? The principle is **never file incorrectly in silence**.

## Tools

```bash
ruff check .      # linting
ruff format .     # formatting
mypy              # strict types
pytest            # tests
pytest --cov      # tests with coverage
```

Everything is configured in `pyproject.toml`. CI uses exactly the same commands.

## Tests

- The core (`domain/`, `services/`) must have tests covering each decision
  branch (moved, unclassified, duplicate, review, quarantine).
- The UI is tested with functional smokes in `tests/test_ui.py`, which skip
  themselves when there is no display (in CI they run under xvfb).
- Core coverage has a floor of 80% (`fail_under` in `pyproject.toml`); CI fails
  if it drops below that.
- The sample fixtures are in `tests/conftest.py`. Never use real data.

## Commits

Conventional Commits format, in English:

```
feat(services): add duplicate detection to the processor
fix(config): keep user config on transient read errors
docs: document the folder template tokens
```
