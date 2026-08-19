# 10. UI shell, views, and controllers

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

The desktop window has a sidebar, a live monitor, a history table, and a settings form that talks to Excel, the filesystem, and SQLite. Tkinter is single-threaded. Widgets that opened `history.db` or walked review folders from a click handler would freeze the UI and smuggle filing-adjacent IO into the view layer.

A single `MainWindow` module that owned all of that was the original shape. It mixed layout with engine lifecycle. Smoke tests had to instantiate everything to change a button label. The engine still needs a home in the UI process, because start/stop and event polling belong next to the window, not inside a Treeview.

## Decision

`src/automator/ui/shell.py` (`MainWindow`) composes. It builds the backend (`open_ledger`, `open_supplier_store`, `ProcessingEngine` with `store.get` and `events.put`), packs `SidebarView` plus the three views, wires controllers, and owns shutdown (`suspend` the bridge, `run_async(engine.stop)`, wait up to `_CLOSE_LIMIT_MS` = 12s, then `close_stores`).

Views live in `ui/views/` (`sidebar.py`, `monitor.py`, `history.py`, `settings.py`, `settings_entities.py`). They take callbacks and `tk.StringVar`s. They contain no SQLite and no engine calls. `MonitorView` logs activity. `HistoryView` renders rows it is given. `SettingsView` holds form variables and society/supplier rows.

Controllers in `ui/controllers/` own IO. `EngineBridge` starts and stops the engine, polls events, and updates the monitor. `HistoryActions` reads the ledger, undoes, clears, and retries. `SettingsForm` collects `AppConfig`, persists via `ConfigStore.update`, and imports societies. `SuppliersController` talks to `SupplierStore` / `SupplierRegistryStore`. `PendingController` counts PDFs under review and quarantine off the Tk thread.

Widgets in `ui/widgets/` (`buttons.py`, `forms.py`, `modal.py`, `tables.py`) are styled controls. Dialogs (`onboarding.py`, `society_dialog.py`, `import_report_dialog.py`) return values. User-facing Spanish copy that is shared (outcome labels, the clear-history confirm) lives in `ui/strings.py`. `OUTCOME_LABELS` maps `ProcessOutcome` to "Archivado", "Revisar", "Cuarentena", and the rest.

`UiMailbox` in `ui/system_utils.py` is a `queue.Queue` of callables. Background work (`run_async`) posts UI updates with `mailbox.post`. `EngineBridge.poll_events` drains the mailbox on the Tk thread next to `EngineEvent`s.

Retry goes through `EngineBridge.start`. `HistoryActions.reprocess_pending` calls the injected `start` callback when the monitor is stopped (after `collect_and_save`). `on_engine_started` then kicks `engine.reprocess_pending()`. If the engine is already running, retry only requeues. That path reuses the ledger check and the "save settings before start" gate on the bridge.

## Consequences

`tests/ui/test_main_window.py` can build `MainWindow` from `ui.shell` and click through smoke paths without each view importing the ledger. A widget change stays in `widgets/`. A new Excel column is a controller plus `services/excel_import.py`.

Controllers still contain Spanish `messagebox` strings that are local to one action. `strings.py` is the home for copy used in more than one place. New UI text stays in Spanish. Identifiers stay in English.

`presentation.py` formats rows and counts PDFs. `PendingController` is the one that calls `count_pdfs` from a worker thread and applies the result on the Tk thread. Views stay out of that.

Close can give up after 12s if the engine is still running, and then skip `close_stores` to avoid joining SQLite from under a live worker. The next launch migrates and reopens `history.db`.

## Alternatives considered

### Fat MainWindow

One module that grids widgets and calls `Ledger.recent` is fewer files. It also makes the 200-line cap impossible and puts IO on the same class that paints the sidebar. Shell compose plus controllers is the split that keeps `make file-size` green.

### Widgets that query SQLite

A history `Treeview` that lazy-loads rows from the db would look simple. It would run SQL on the Tk thread and couple the widget to `history.db`'s schema. `HistoryActions.refresh` pulls `ledger.recent()`, maps through `history_row`, and hands tuples to the view.

### View calling `engine.start` for retry

A retry button bound straight at `ProcessingEngine.start` would skip `EngineBridge.require_ledger` and `SettingsForm.collect_and_save`. Retry would then run on stale folders or without duplicate detection. The start callback injected into `HistoryActions` is the same `EngineBridge.start` the toggle button uses.
