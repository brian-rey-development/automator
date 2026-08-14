# CLAUDE.md

Guide for working in this repository. It extends the user's global instructions;
on conflict, this file wins for anything project-specific.

## What it is

Automator (author: Brian Rey) is a desktop application that watches a downloads
folder, reads each AFIP invoice PDF, detects the voucher type, number, supplier
and buying company (by CUIT), and files the renamed PDF into the right folder.
It is packaged as a Windows `.exe`.

## Guiding principle

**No invoice is ever misfiled or lost silently.** On any uncertainty (supplier
not detected, ambiguous buyer, unreadable PDF), the file goes to review or
quarantine, never to a destination guessed with an "ok". Every change must
preserve this invariant.

## Commands

```bash
make install    # create .venv and install app + dev deps
make run        # run the app (same as python -m automator)
make demo       # generate sample invoices and open the app
make check      # lint + types + tests (run before committing)
make build      # generate the icon and the .exe with PyInstaller
```

Standalone tools: `ruff check .`, `ruff format .`, `mypy`, `pytest`.

## Architecture

Three layers, dependencies pointing inward (ui -> services -> domain):

- `src/automator/domain/` - pure logic, no side effects, 100% testable (models,
  parser, classification, naming). Never does IO.
- `src/automator/services/` - IO and orchestration: PDF reading, file operations,
  watcher, processing engine and ledger (history in SQLite).
- `src/automator/ui/` - CustomTkinter interface. Contains no business rules.
- `src/automator/config.py` - validated, immutable configuration model and its
  atomic persistence.

### Concurrency model

The engine (`services/engine.py`) runs on a background thread with a queue. The
UI talks to it via `EngineEvent` on a `queue.Queue` drained only from the Tkinter
thread (`_poll_events`). **Tkinter is not thread-safe: never touch widgets from a
thread other than the main one.** The queue and the stop signal are recreated on
every start ("generation") so an old worker never shares a queue with a new one.

### On-disk data

- Config: `config.json` in the user's config directory (platformdirs).
- History: `history.db` (SQLite) in the user's data directory.
- Logs: rotating `automator.log` in the user's log directory.

Paths resolved in `config.py` (`config_path`, `ledger_path`, `log_dir`).

## Code conventions

- **Identifiers and comments in English.** Comment only the non-obvious why (an
  invariant, a workaround), never what the code already says.
- User-facing strings stay in Spanish (the app's end users are Spanish speakers):
  UI labels, dialog messages and notifications are Spanish; comments and docs are
  English.
- Strict typing: `mypy --strict`, no unjustified `Any`.
- Functions <= 20 lines, early returns, immutability by default.
- No em dashes in any text (prose, docs, commits). Use regular hyphens.
- Validate at the boundaries (user input, external APIs); trust the interior.
- `AppConfig` and `SocietyMapping` are `frozen`: to change the config you build a
  new object, you do not mutate it. `ConfigStore.get()` returns the shared snapshot.

## Testing

- The core (`domain/` and `services/`) is tested with pytest; aim to cover every
  decision branch of processing (moved, unclassified, duplicate, review,
  quarantine).
- The UI has functional smoke tests in `tests/test_ui.py` that skip themselves
  when there is no display (they run under xvfb in CI). When touching the UI, run
  a smoke that builds `MainWindow` without exceptions.
- `tests/conftest.py` has sample invoice texts and a `make_config` factory.

## Gotchas

- File moves use `shutil.move` (works across drives) and never overwrite (suffix
  ` (n)`). Copy mode uses `shutil.copy2` and leaves the original in place.
- In copy mode the original stays in the input folder, so the engine records a
  stable source signature (path, size, mtime) in the ledger to avoid reprocessing.
- Windows: long-path prefix and the `\\?\UNC\` form for network paths (`file_ops`).
- The parser never raises: on unexpected text it returns deterministic defaults.
- Duplicate detection uses the identity `supplier|number|type` against the ledger;
  only MOVED/UNCLASSIFIED results count as "already filed".

## Structure

```
src/automator/      source code (domain / services / ui / config)
tests/              core and services test suite
scripts/            generators (icon, sample invoices) and Windows build
installer/          Inno Setup script for the installer
assets/             brand icon (.ico / .png)
docs/               architecture, features and configuration
```
</content>
