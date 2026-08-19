# 1. Layered architecture

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

Automator is a desktop filer. It watches a folder, reads AFIP invoice PDFs, decides a destination, and moves or copies the file. The same product also has a CustomTkinter UI, SQLite history, a config file, and a Windows `.exe`. Filing mistakes are expensive because the user trusts the archive. That combination needs a structure where policy can be tested without disks, and where the UI cannot invent a destination.

A single package that mixed Tk widgets with PDF IO and SQLite would make the invariant (an uncertain invoice goes to review) untestable except through the window. The opposite extreme, a full hexagonal ports-and-adapters stack, would add interfaces for a one-process desktop app that already has a clear inside.

## Decision

The code lives in three layers with dependencies pointing inward, plus two supporting modules beside them.

`src/automator/domain/` is pure logic. It owns models (`ParsedInvoice`, `ProcessOutcome`, `ProcessResult`), parsing, buyer resolution, supplier matching, filenames, and filing policy (`decide_filing`). It composes `pathlib.Path` values. It performs no IO.

`src/automator/services/` owns side effects and orchestration. PDF reading, file moves and copies, the engine (`engine/lifecycle.py`, `runtime.py`, `worker.py`), `InvoiceProcessor`, the SQLite ledger, and the supplier store live here. Services import domain. Domain is unaware of services.

`src/automator/ui/` is the CustomTkinter shell. It imports services and domain to display state and to start actions. It contains no filing rules.

`src/automator/config/` holds the frozen `AppConfig` / `SocietyMapping` model and `ConfigStore`. `src/automator/paths.py` resolves `config.json`, `history.db`, logs, and assets. Config may import domain (CUIT and name types). Config is forbidden from importing services. Domain is forbidden from importing config.

`tool.importlinter` in `pyproject.toml` encodes this as a layers contract (`automator.ui` -> `automator.services` -> `automator.domain`) plus the two forbidden contracts above. `scripts/check_file_size.py` caps every production module at 200 lines (`MAX_LINES = 200`, empty allowlist). `make check` runs both.

## Consequences

Filing policy is unit-tested in `tests/domain/` with no temp directories. Processor and engine tests in `tests/services/` inject extractors and fake watchers. The UI stays a client of `ProcessingEngine` and `ConfigStore`.

A new feature has a home. A new match rule goes in domain. A new disk behavior goes in services. A new screen goes in `ui/views/` with a controller if it needs IO. Crossing a layer is a `lint-imports` failure, so a widget cannot grow a SQLite query by accident.

The 200-line cap is a real constraint. `InvoiceProcessor` already has a per-file ruff ignore because orchestration is dense. Splitting further is the intended pressure, not raising the cap.

Config sits outside the three-layer list. That is deliberate. It is shared state for UI and worker, not a fourth ring, and the forbidden contracts keep it from becoming a services dump.

## Alternatives considered

### Hexagonal ports and adapters

A ports layer would give `decide_filing` an even stricter wall. For a single-process desktop app with one worker thread, the extra interfaces would mostly wrap functions that already exist (`extract_text`, `Ledger.archived_destination`). Import-linter plus the 200-line cap already keep the inside small enough to test.

### UI talking straight to SQLite and the filesystem

A fat `MainWindow` that files PDFs from a button handler would make every policy change a UI test. Tkinter is also not thread-safe, so the watcher would have nowhere honest to report. The engine/event queue exists because the UI is a layer, not a peer of the worker.

### Domain that writes files

Putting `shutil.move` next to `decide_filing` would force every reliability test onto disk. Path composition stays in domain (`destination_dir`, `FilingFolders`) because a destination is a value. The write itself stays in `services/processing/placement.py`.
