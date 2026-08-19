# Architecture

Automator separates pure logic from side effects and from the interface, into
three layers with dependencies pointing inward: `ui -> services -> domain`. The
core has no knowledge of a graphical interface or a disk.

```
src/automator/
  domain/           Pure, 100% testable logic (no IO)
    parser/         AFIP invoice and purchase-order extraction
    filing/         decide_filing, destination template, reliability
    buyer.py        CUIT then fuzzy name match (threshold 0.90, margin 0.05)
    suppliers.py    registry matching that never guesses on collisions
  services/
    engine/         lifecycle, worker, inbox, source memory, events
    processing/     processor orchestration and placement
    persistence/    WAL connections and additive migrations
    undo.py         move back + mark_reverted with restore on mark failure
  ui/
    shell.py        compose, nav, shutdown
    views/          sidebar, monitor, history, settings
    controllers/    engine bridge, history, settings, suppliers, pending
    widgets/        buttons, modal, forms
    dialogs/        onboarding, society, import report
  config/           AppConfig, store, folder-name defaults
  paths.py          config/data/log/assets locations
```

## Domain layer (`domain/`)

Pure, deterministic functions with no side effects:

- `models.py` - immutable models: `Voucher`, `ParsedInvoice`, `ProcessOutcome`,
  `ProcessResult`. `ParsedInvoice` exposes derived properties (`has_number`,
  `has_supplier`, `identity`, `type_label`).
- `parser/` - extracts type/letter (by AFIP code with a text-based fallback),
  number, supplier, buyer CUIT and date. **Never raises**: when it encounters
  unexpected text it returns deterministic defaults. Purchase orders are
  header-anchored, not a free substring.
- `filing/` - `decide_filing` is the policy. Destination templates ignore
  unknown tokens. Reliability matches own societies by normalized legal name,
  trade name and aliases.
- `filenames.py` - name sanitizing for Windows and assembly of the final name.

Fuzzy buyer matches file as `MOVED` with an auditable message. That is a
product decision: the runner-up is never chosen.

## Services layer (`services/`)

- `pdf_reader.py` - extracts text with deterministic file closing and
  per-page resilience.
- `file_ops.py` - atomic moves and copies, no overwriting, samefile no-op,
  long paths and UNC on Windows.
- `watcher.py` - watches the input folder (watchdog), injectable into the engine.
- `processing/` - reads, parses, classifies, then places. Policy is in domain.
- `engine/` - supervisor of generations: queue, worker, rescanner, source memory.
- `ledger.py` - audit history in SQLite. Schema is versioned. Duplicate check
  is identity **or** `(issuer_cuit, number, type)`.
- `undo.py` - move back to input, then mark reverted. If the mark fails, the
  file is restored.

## Interface layer (`ui/`)

CustomTkinter. It contains no business rules: it only displays state and
triggers engine actions. `shell.py` composes. Views take callbacks.
Controllers own Excel, history and engine IO. Background results return
through `UiMailbox`, drained on the Tk thread. `EngineBridge.poll_events`
is the pump.

## Concurrency model

```
watcher (thread) ─┐
                  ├─> queue.Queue ─> worker (thread) ─> EngineEvent ─┐
rescan (thread)  ─┘                                                  │
                                                                     v
                              event queue.Queue <── UI (Tkinter thread)
                          EngineBridge.poll_events (after 150ms)
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
