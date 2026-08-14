# Architecture

Automator separates pure logic from side effects and from the interface, into
three layers with dependencies pointing inward: `ui -> services -> domain`. The
core has no knowledge of a graphical interface or a disk.

```
src/automator/
  domain/      Pure, 100% testable logic (no IO)
  services/    IO and orchestration (PDF, files, watcher, engine, history)
  ui/          Desktop interface (CustomTkinter)
  config.py    Validated, immutable configuration model + persistence
```

## Domain layer (`domain/`)

Pure, deterministic functions with no side effects:

- `models.py` - immutable models: `Voucher`, `ParsedInvoice`, `ProcessOutcome`,
  `ProcessResult`. `ParsedInvoice` exposes derived properties (`has_number`,
  `has_supplier`, `identity`).
- `parser.py` - extracts type/letter (by AFIP code with a text-based fallback),
  number, supplier, buyer CUIT and date. **Never raises**: when it encounters
  unexpected text it returns deterministic defaults.
- `classifier.py` - resolves the destination folder by applying the template.
- `filenames.py` - name sanitizing for Windows and assembly of the final name.

## Services layer (`services/`)

- `pdf_reader.py` - extracts text with deterministic file closing and
  per-page resilience.
- `file_ops.py` - atomic moves, no overwriting, with support for long paths
  and UNC on Windows.
- `watcher.py` - watches the input folder (watchdog).
- `processor.py` - orchestrates the processing of a PDF and decides its
  destination.
- `engine.py` - background engine: queue, worker, periodic rescan.
- `ledger.py` - audit history in SQLite (basis for history, duplicates and
  undo).

## Interface layer (`ui/`)

CustomTkinter. It contains no business rules: it only displays state and
triggers engine actions. `main_window.py` coordinates; `onboarding.py` and
`society_dialog.py` are dialogs; `theme.py` is the design system;
`system_utils.py` opens folders and shows notifications.

## Concurrency model

```
watcher (thread) ─┐
                  ├─> queue.Queue ─> worker (thread) ─> EngineEvent ─┐
rescan (thread)  ─┘                                                  │
                                                                     v
                              event queue.Queue <── UI (Tkinter thread)
                                    _poll_events (after 150ms)
```

- The engine runs on a background thread; the UI never blocks.
- Engine -> UI communication happens via `EngineEvent` on a queue that is drained
  only from the Tkinter thread. **Tkinter is not thread-safe.**
- The work queue and the stop signal are recreated on every startup
  ("generation"): an old worker that is slow to finish never shares a queue
  with a new one, and a new startup is rejected while the previous one is still
  alive.
- A `set` of in-flight files prevents queuing the same PDF twice.

## Flow of a file

```
new PDF -> wait_until_stable -> extract_text
        -> parse_invoice
        -> ambiguous?    -> _PARA_REVISAR
        -> not reliable? -> _PARA_REVISAR
        -> duplicate?    -> _DUPLICADOS
        -> no CUIT?      -> _SIN_CLASIFICAR
        -> ok            -> society folder (per template)
        (unreadable/error) -> _ERRORES (quarantine)
```

Every result is recorded in the ledger, no matter what happens (except files
that no longer exist).

## Persistence

- Configuration: `config.json` (atomic save, recovery from corruption).
- History: `history.db` (SQLite).
- Logs: rotating `automator.log`.

Paths are resolved with `platformdirs` (`config_path`, `ledger_path`,
`log_dir`), so they follow the conventions of each operating system.
