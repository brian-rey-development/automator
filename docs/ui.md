# Interface

The desktop UI is CustomTkinter. Identifiers, comments and module names stay in
English. Every string the user sees (labels, buttons, dialogs, notifications) is
Spanish and lives in the view, dialog or `strings.py`. The layer displays state
and fires callbacks. Filing policy, Excel parsing and SQLite stay in
`domain/` and `services/`.

`python -m automator` and the `automator` / `automator-cli` entry points all
call `automator.ui.app:main`.

## Entry and first run

`app.py` sets up logging, applies `init_appearance()` (light CustomTkinter,
blue default theme) and opens a centered 1080x700 window titled
`Automator - Clasificador de facturas AFIP` (minimum 980x640). It loads
`ConfigStore` through `load_store()` and builds `MainWindow`. Closing the
window goes through `MainWindow.on_close`.

First run is `config_path()` missing. `MainWindow` then schedules
`OnboardingDialog` 250 ms after boot. If the wizard returns an `AppConfig`,
`SettingsForm.persist` writes it and the form reloads.

## Shell

`shell.py` owns composition, navigation and shutdown. `MainWindow` is a
`CTkFrame` that opens the stores, builds the sidebar plus the three content
views, wires controllers and starts the event pump.

| Piece | Role |
|---|---|
| `_init_backend` | `UiMailbox`, engine event queue, `open_ledger` / `open_supplier_store`, `ProcessingEngine` |
| `_build` / `_add_views` | `SidebarView` on the left, `MonitorView` / `HistoryView` / `SettingsView` stacked on the right |
| `_wire` | Controllers, `SettingsHooks`, engine/history/pending callbacks |
| `_show(key)` | Grids one view, hides the others, highlights the sidebar. Opening `history` refreshes the table |
| `_boot` | Loads settings, starts `poll_events` every 150 ms, starts pending counts, optional onboarding |
| `on_close` | Suspends the bridge and pending poll, stops the engine on a worker thread, waits up to 12 s in 50 ms steps, then `close_stores` and destroys the window |

Nav keys are `monitor`, `history` and `config`. `_settings_hooks()` is the
only place that binds settings buttons to controllers.

## Screens

Views take callbacks and stay free of business rules. They render widgets and
call the hooks they were given.

### Monitor (`views/monitor.py`)

Session dashboard. `on_toggle` starts or stops the engine.
`on_open_review` is the pending banner.

The user can start and stop the watcher (`Iniciar` / `Detener`), read four
session counters (Detectados, Archivados, Para revisar, Errores) and follow
the recent-activity table (up to 500 rows). While the engine is running the
toggle uses `Palette.ERROR` / `Palette.ERROR_HOVER` with
`Palette.ON_PRIMARY` text. A banner appears when review or quarantine still
holds PDFs. The copy counts those folders separately (`3 para revisar`,
`2 en cuarentena`). **Abrir pendientes** opens the folder that still has
files (both, when both do).

`presentation.count_key` maps a `ProcessResult` onto the four counters.
`EngineBridge` drops `SKIPPED_MISSING` before it reaches those counters.

### History (`views/history.py`)

Ledger table plus toolbar. Callbacks are retry, undo, refresh and clear.

The user can **Reintentar pendientes**, **Deshacer ultimo movimiento**,
**Actualizar** and **Vaciar historial**. Rows come from `presentation.history_row`
(timestamp, file, voucher, Spanish status, destination). A reverted row is
tagged `warn` and the status reads `(deshecho)`. Buttons enable only when
the controller says they can: undo and clear need the monitor stopped;
retry needs a pending count above zero.

### Configuration (`views/settings.py`, `views/settings_entities.py`)

Scrollable form driven by `SettingsHooks`. The view holds `StringVar` /
`BooleanVar` fields and paints companies and suppliers. SQLite and the
engine stay in the controllers.

The user can pick and open the input and output folders, add or import
companies, search / import / clear / remove suppliers, toggle dry-run, copy
mode and notifications, then **Guardar**. **Avanzado** starts collapsed and
reveals download wait, timeout, the folder template, unclassified /
quarantine / purchase-order folders, and **Abrir carpeta de logs**.

`settings_entities.py` builds the two entity cards: company rows with
Editar / Eliminar, supplier rows with search (`Buscar proveedor...`) and
Eliminar. Supplier search is limited to 20 hits; the header reads
`Mostrando N de T`.

### Sidebar (`views/sidebar.py`)

Brand mark, version, the three nav items (`Monitor`, `Historial`,
`Configuracion`) and a status pill (`Detenido` / `En ejecucion` /
`Iniciando...` / `Deteniendo...`). `highlight` paints the active strip with
`Palette.ACCENT` and the label with `Palette.ON_PRIMARY`.

## Controllers

Controllers own IO. They talk to the engine, ledger, Excel and the
filesystem, then push results onto the views from the Tk thread.

### `EngineBridge` (`controllers/engine_bridge.py`)

Start, stop and event pumping.

- `require_ledger(available)` records whether `open_ledger` succeeded. `start`
  refuses to run without a ledger and shows a Spanish error: duplicates and
  undo would be unavailable.
- `start` saves the settings form first, disables the toggle, then
  `run_async(self._engine.start)`. `toggle` starts or stops.
- `poll_events` drains `EngineEvent`s and `UiMailbox` every 150 ms. It is
  the only pump; `shell._boot` schedules the first tick.
- `STARTED` stores `event.generation_id`, resets session stats, marks the
  UI running and fires `on_started`. Later events whose `generation_id`
  differs from that value are ignored, so a dying generation cannot paint
  the next one.
- `RESULT` increments `count_key`, appends a monitor row and fires
  `on_result`. `STOPPED` may restart if `SettingsForm.consume_restart()`
  is set (save-while-running). `ERROR` without a path is a start failure
  messagebox; with a path it is a session error row.

The shell binds `on_started` to `HistoryActions.on_engine_started`,
`on_result` to a history refresh when that view is visible, and
`on_running_changed` to `HistoryActions.update_actions`. Clearing history
calls `reset_session_stats`.

### `HistoryActions` (`controllers/history_actions.py`)

- **Undo** calls `perform_undo` on `ledger.last_undoable()`. The monitor
  must be stopped so the returned PDF is not picked up immediately.
- **Retry** uses `EngineBridge.start`. If the engine is already running it
  requeues at once. Otherwise it saves config, sets `_retry_when_started`
  and starts; `on_engine_started` then calls `ProcessingEngine.reprocess_pending`
  on a worker and posts the count through the mailbox.
- **Vaciar historial** asks for confirm (`CLEAR_HISTORY_CONFIRM` in
  `strings.py`), clears the ledger only and leaves PDFs where they are.
  `on_cleared` resets the session counters.

### `SettingsForm` (`controllers/settings_form.py`)

Loads `AppConfig` into the view, collects it back and persists through
`ConfigStore.update`. Empty folder fields and a bad timeout are rejected
before pydantic. Saving while the monitor is running stops it and sets
`_restart_after_save` so the bridge starts again on `STOPPED`.

Company add / edit opens `SocietyDialog`. Remove asks for confirm. Excel
import runs off the Tk thread and applies through the mailbox. Folder
**Elegir** uses `ask_folder`; **Abrir** and **Abrir carpeta de logs** use
`reveal_folder`. Logs resolve through `paths.log_dir`.

### `SuppliersController` (`controllers/suppliers.py`)

Import, search, remove and clear against `SupplierStore` plus the
in-memory `SupplierRegistryStore` snapshot the worker reads. Import parses
on a worker, upserts, reloads the snapshot and opens `ImportReportDialog`
from the mailbox. Vaciar and Eliminar confirm first.

### `PendingController` (`controllers/pending.py`)

Every 5 s a worker counts PDFs in `review_folder` and `quarantine_folder`
(`presentation.count_pdfs`, recursive). The Tk tick applies
`MonitorView.set_pending(review, quarantine)` and forwards the total to
`HistoryActions.set_pending` (retry enablement). When the total rises and
`config.notify` is on, `notify` fires a system notice. **Abrir pendientes**
calls `open_review`: quarantine only opens quarantine, both open both,
otherwise review.

## Widgets and theme

`widgets/` is the shared kit. Clicks go through the factories in
`widgets/buttons.py`.

| Factory | Use |
|---|---|
| `primary_button` | Accent actions (Iniciar, Guardar, Empezar) |
| `secondary_button` | Dark fill, `Palette.ON_PRIMARY` text (Agregar empresa, Entendido) |
| `danger_button` | `Palette.ERROR` / `Palette.ERROR_HOVER` / `Palette.ON_PRIMARY` |
| `nav_button` | Sidebar items |
| `ghost_button` | Avanzado, Actualizar, Vaciar historial |
| `path_button` | Elegir, Abrir, Importar Excel, Abrir pendientes |
| `row_button` | Editar / Eliminar on entity rows |
| `muted_button` | Dialog dismiss (Lo hago despues, Cancelar) |

`widgets/forms.py` has `folder_field` (label, path entry, Elegir, Abrir),
`card_body`, `checkbox`, `hint`, `entity_row` and `template_field`.
`widgets/tables.py` builds `status_tree` (`ttk.Treeview` style
`Activity.Treeview`) with `ok` / `warn` / `error` row tags.
`widgets/modal.py` `make_modal` transients a `CTkToplevel`, binds Return /
Escape and grabs focus.

`theme.py` is the design system: warm paper `Palette.BG`, almost-black
sidebar, chartreuse `Palette.ACCENT`, `Palette.ON_PRIMARY` for text on dark
or error fills, `Palette.ERROR_HOVER` for destructive hover. `make_fonts`
prefers Segoe UI. `configure_table_style` skins the activity and history
trees. `create_brand_mark` draws the sidebar bolt.

`presentation.py` formats CUIT (`30-11111111-8`), history rows and
validation errors. `strings.py` holds `OUTCOME_LABELS` (Archivado, Revisar,
Cuarentena, ...) and `OUTCOME_ROW_TAG`. `pickers.py` wraps
`filedialog.askopenfilename` (Excel `*.xlsx`) and `askdirectory`.

## Dialogs

| Dialog | File | What the user does |
|---|---|---|
| `OnboardingDialog` | `dialogs/onboarding.py` | First-run minimum: input folder, output folder, optional first company (CUIT + razon social). **Empezar** validates; **Lo hago despues** closes with no result |
| `SocietyDialog` | `dialogs/society_dialog.py` | Create or edit a buyer: CUIT, razon social, optional trade name and comma-separated aliases. Returns a validated `SocietyMapping` |
| `ImportReportDialog` | `dialogs/import_report_dialog.py` | After Excel import, shows created / updated / invalid counts and up to 30 rejected rows |

All three go through `make_modal`.

## Threading and stores

Tkinter is not thread-safe. Workers post work; the Tk thread applies it.

`system_utils.UiMailbox` is a `queue.Queue` of zero-argument callables.
`post` is safe from any thread. `drain` runs them on the caller, which is
always `EngineBridge.poll_events` on the Tk thread. Excel import, retry
counts and settings apply go `run_async` then `mailbox.post`.

`backend.py` opens the two SQLite handles the window needs:

- `open_ledger()` -> `Ledger(ledger_path())` or `None` on `OSError` /
  `sqlite3.Error`
- `open_supplier_store()` -> `SupplierStore(ledger_path())` or `None`
- `close_stores(ledger, suppliers)` closes whichever opened

A missing ledger still builds the window. `EngineBridge.require_ledger(False)`
blocks Start.

## Opening folders

`system_utils.open_folder(path)` returns `bool`: `False` when the path is
missing or the OS open fails (`os.startfile` on Windows, `open` on macOS,
`xdg-open` elsewhere). `reveal_folder` is the user-facing wrapper. It shows
a Spanish `messagebox` when the field is empty (`Elegi una carpeta primero.`),
the path is missing (`No existe: ...`) or `open_folder` fails
(`No se pudo abrir: ...`). Settings **Abrir**, logs and the pending banner
all go through `reveal_folder`.

`notify` is best-effort (osascript on macOS, a PowerShell tray balloon on
Windows) and is used only by `PendingController` when pending items increase.
