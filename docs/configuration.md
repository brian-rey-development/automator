# Configuration

All configuration is edited from the interface (Configuration tab) and saved in
`config.json`. `AppConfig` and `SocietyMapping` are frozen Pydantic models: a
change builds a new object rather than mutating the live one.
`ConfigStore.get()` returns that shared snapshot. The engine and the processor
read it through a `ConfigProvider` (`Callable[[], AppConfig]`) so they always
see the current value.

## File locations

Paths follow each operating system's conventions (via `platformdirs`), resolved
in `src/automator/paths.py`:

- **Configuration**: `config.json` in the user's config directory
  (`config_path()`).
- **History and supplier registry**: `history.db` in the user's data directory
  (`ledger_path()`).
- **Logs**: rotating `automator.log` in the user's log directory (`log_dir()`).
- **Assets**: bundled next to the package, or under PyInstaller's `_MEIPASS`
  when frozen.

From the app: Configuration -> Avanzado -> "Abrir carpeta de logs".

`ConfigStore` saves atomically (write a temp file, fsync, `os.replace`). If
`config.json` is missing, the default is written on first load. Invalid content
is renamed to `config.json.YYYYMMDD-HHMMSS.corrupt` and the default is used so
the app still opens. A transient read error (lock, permissions, network drive)
leaves the file untouched and uses the default only in memory.

Folder creation lives in `services/folders.py` (`ensure_folders`). The input
folder is created if needed; the other folders are best-effort and are created
again at archive time if that first pass failed.

## Fields

### Main folders

- **Input folder** (`input_folder`): where downloaded PDFs land (this is the
  folder being watched). Default: the user's Downloads directory.
- **Output folder** (`base_output_folder`): root where the sorted invoices are
  stored. Default: `~/Automator/Facturas ordenadas`.

### Companies

List of buyer companies (`societies`). Each `SocietyMapping` has:

- **CUIT**: 11 digits (hyphens, dots and spaces are accepted, then normalized).
  The AFIP check digit is required.
- **Company name** (`name`, Razon Social): visible name, and the folder
  component. Empty names are rejected.
- **Trade name** (`trade_name` / `nombre_fantasia`) and **aliases**: optional,
  used to match the buyer by name when the CUIT is absent from the PDF.

The destination folder is derived: `base/{Razon Social}`. Companies are added,
edited and removed from the interface, or imported from Excel. The app starts
with an empty list; you define your own.

### Suppliers

Registry of invoice issuers, imported from Excel and stored in the `suppliers`
table of `history.db`. Each supplier has a CUIT, legal name, optional trade name
and alias variants. When a known supplier is found in an invoice (by CUIT, then
by a unique alias of at least five characters), its legal name canonicalizes
the filing. The registry is searched from the interface and can be cleared. It
is optional: if the registry is empty, filing uses the label read from the PDF.

### Options

- **Test mode** (`dry_run`): moves nothing, only shows what it would do.
  Default: off.
- **Copy instead of move** (`copy_files`): leaves the original in the input
  folder and places a copy in the destination. The app remembers each
  already-processed file (by path, size and mtime) so a later rescan skips it.
  Default: off (it moves, and the input folder empties itself).
- **Wait for the download to finish** (`wait_for_stability`): waits until the
  file size stops changing. Default: on.
- **Maximum wait (seconds)** (`stability_timeout_s`): 0 to 120. Default: 10.
- **Notifications** (`notify`): system notice when pending items increase.
  Default: on.
- **Folder structure** (`destination_template`): template inside each company's
  folder. Default: `{supplier}`.

### Automatic folders (advanced)

These names stay in Spanish. `_PARA_REVISAR` and `_DUPLICADOS` are derived from
the output base (`review_folder`, `duplicates_folder`); they are properties on
`AppConfig`.

- **Unclassified** (`unknown_folder`): invoices whose buyer CUIT is unknown.
  Default: `{output}/_SIN_CLASIFICAR`.
- **Quarantine** (`quarantine_folder`): unreadable PDFs or PDFs with errors.
  Default: `{output}/_ERRORES`.
- **Purchase orders** (`orders_folder`): archive root for `ORDEN DE COMPRA`
  documents. Default: `~/Automator/Ordenes de compra`. When the buyer is
  unknown, the company segment is `ORDERS_UNKNOWN_FOLDER_NAME`
  (`_SIN_SOCIEDAD`).

`ensure_folders` also creates `_PARA_REVISAR` and `_DUPLICADOS` under the output
folder, plus each configured company's folder.

## Folder template

Defines subfolders inside each company's folder (or inside the orders base for
purchase orders). Valid tokens:

| Token | Value |
|---|---|
| `{supplier}` | Supplier company name |
| `{society}` | Name of the company folder |
| `{year}` | Year of the issue date (or `sin_fecha`) |
| `{month}` | Month (or `sin_fecha`) |
| `{day}` | Day (or `sin_fecha`) |

Examples:

- `{supplier}` (the default) -> `.../Company/SUPPLIER/invoice.pdf`
- `{year}/{month}/{supplier}` -> `.../Company/2026/08/SUPPLIER/invoice.pdf`

An unknown token is rejected on save. Empty segments after expansion are
dropped.

## Validation rules

- Output folders (the base, unclassified, quarantine, orders, and each company
  folder) cannot sit inside the input folder. That constraint blocks a
  reprocessing loop.
- CUITs cannot be repeated across companies, and every CUIT (companies and
  suppliers) must pass the AFIP check digit.
- The destination template may only use the tokens listed above.
- Razon social is required and non-empty. All folder fields are required in the
  form.

On a validation error, the interface reports it and withholds the save until it
is fixed. `ConfigStore.update` writes disk first, then replaces the in-memory
snapshot, so a failed save leaves memory unchanged.
