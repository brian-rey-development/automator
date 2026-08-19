# Automator - AFIP invoice classifier

Author: Brian Rey

Desktop application that watches a downloads folder, reads each AFIP invoice
PDF, detects the voucher type, number, supplier and buying company (by CUIT),
and files the renamed PDF into the right folder (`base/{empresa}/{proveedor}`).
Two categories drive filing: **companies** (buyers, in `config.json`) and an
Excel-imported **supplier registry** (issuers, in SQLite) that canonicalizes the
supplier name by matching the invoice text against known CUITs and aliases.

It ships empty of companies and CUITs. Everything is configured from the
interface. On first launch, a wizard collects the input folder, the output
folder and, optionally, a first company. The app is packaged as a Windows
`.exe`.

## Guiding principle

**No invoice is ever misfiled or lost silently.** On any uncertainty (supplier
not detected, ambiguous buyer, unreadable PDF), the file goes to review or
quarantine, never to a destination guessed with an "ok". Every change must
preserve this invariant.

## Features

- CustomTkinter interface with folder pickers, help text and a first-run wizard.
- Voucher type and letter detection by AFIP code, with a text-based fallback.
  Purchase orders are recognized from a header-anchored "ORDEN DE COMPRA".
- Routing by CUIT to each company folder. A buyer matched only by name (fuzzy,
  threshold 0.90) goes to `_PARA_REVISAR` so a human can confirm the company.
- Supplier registry imported from Excel. A known CUIT or unique alias
  canonicalizes the filing name so every variant of the same issuer lands in one
  folder.
- Configurable folder structure via a template (`{supplier}`, and optionally
  `{year}`, `{month}`, `{day}`, `{society}`).
- Persistent audit history in SQLite. Undo returns the last placement to the
  input folder. Retry walks `_PARA_REVISAR` and `_ERRORES` recursively after you
  adjust the configuration.
- Duplicate detection by `normalize_name(supplier)|number|type`, plus the exact
  `issuer_cuit|number|type` key when the issuer CUIT is present. Only MOVED and
  UNCLASSIFIED results count as already filed.
- Automatic `_PARA_REVISAR` when extraction is incomplete, several of your own
  companies appear, or the buyer is a fuzzy name match.
- Persistent pending notice read from the folders, with an optional system
  notification when the count rises.
- Processes whatever was already in the input folder on startup and retries
  leftover files on a periodic rescan.
- Waits for the download to finish before moving, so a half-written PDF stays
  put until it is stable.
- Unique destinations: if the name already exists, the file is saved as
  ` (2)`, ` (3)`, and so on.
- Automatic quarantine of unreadable or failing PDFs. The monitor keeps running.
- Validated, immutable configuration (`AppConfig` and `SocietyMapping` are
  frozen), saved atomically, with recovery if `config.json` is corrupted.
- Dry-run mode to preview the destination while leaving files in place, copy
  mode that leaves the original in the input folder, and rotating logs.

## Requirements

- Python 3.11 or newer.
- Windows for the final executable (the code also runs on macOS and Linux).

## Development usage

With `make` (recommended):

```bash
make install   # creates the virtual environment and installs everything
make run       # runs the application
make demo      # generates sample invoices and opens the app to try it
make check     # linting + types + tests + coverage + layer contracts + file size
```

`make demo` creates sample PDFs in the configured input folder covering every
case (filed by company, unclassified, to review and quarantine). When the app
opens, press "Iniciar" to watch them being processed in real time.

Using the venv directly:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m automator
```

On macOS or Linux the equivalent is `python3 -m venv .venv && source .venv/bin/activate`.
With [uv](https://docs.astral.sh/uv/), `uv pip install -e ".[dev]"` works too.

For a bit-for-bit reproducible install there is a lockfile (`uv.lock`): with
[uv](https://docs.astral.sh/uv/), `uv sync --extra dev` installs exactly the same
versions. Regenerate the lock with `make lock` when dependencies change.

To install the quality hooks before each commit: `pre-commit install`.

## Building the Windows executable

```powershell
.\scripts\build_windows.ps1
```

The executable lands in `dist\Automator.exe`. It is a single, console-less file
that can be copied and run on any Windows PC. The script generates the brand icon
(`assets\automator.ico`) first. `make build` does the same from a Unix-like
environment (icon, then PyInstaller).

### Installer (optional)

With [Inno Setup](https://jrsoftware.org/isinfo.php) installed, build the
installer with a start-menu shortcut and an auto-start option:

```powershell
iscc installer\automator.iss
```

It lands in `dist\installer\Automator-Setup-1.1.0.exe`.

## Quality

```bash
ruff check .      # linting (fast)
ruff format .     # formatting
mypy              # strict types
pytest            # tests with core coverage
```

`make check` also runs import-linter (`ui -> services -> domain`) and
`scripts/check_file_size.py` (production modules stay at or under 200 lines).

Continuous integration runs the same commands on Python 3.11, 3.12 and 3.13
(UI smoke tests run under xvfb), plus a Windows job that builds the executable
on every push. Core coverage has a 90% floor (`fail_under` in `pyproject.toml`);
the UI package is omitted from that measurement. The `automator-cli` entry point
is an alias of the desktop app.

## Architecture

Three layers, dependencies pointing inward (`ui -> services -> domain`):

```
src/automator/
  domain/           Parser, filing policy, models, buyer, suppliers (pure logic)
    parser/         AFIP invoice and purchase-order extraction
    filing/         decide_filing, destination template, reliability
  services/         Engine, processing, persistence, file IO
    engine/         Lifecycle, worker, inbox, source memory, events
    processing/     Processor orchestration and placement
    persistence/    SQLite WAL connections and migrations
  ui/               Shell, views, controllers, widgets, dialogs (CustomTkinter)
  config/           Frozen AppConfig, atomic store, folder-name defaults
  paths.py          Config, data, log and asset locations
tests/              Mirrors the layers (domain, services, ui, config)
```

The engine runs on a background thread and talks to the interface through an
event queue drained only from the Tkinter thread. Filing decisions live in
`domain/filing/decide_filing`. See [docs/architecture.md](docs/architecture.md)
and [docs/how-it-works.md](docs/how-it-works.md) for the full map.

## Documentation

- [`docs/README.md`](docs/README.md) - index of every document.
- [`docs/architecture.md`](docs/architecture.md) - layers, packages and flow.
- [`docs/how-it-works.md`](docs/how-it-works.md) - path of a PDF from inbox to folder.
- [`docs/features.md`](docs/features.md) - product behavior in detail.
- [`docs/configuration.md`](docs/configuration.md) - fields, folders and the template.
- [`docs/data-model.md`](docs/data-model.md) - domain models and identities.
- [`docs/persistence.md`](docs/persistence.md) - config.json, history.db and logs.
- [`docs/concurrency.md`](docs/concurrency.md) - engine thread, queues and Tkinter.
- [`docs/invariant.md`](docs/invariant.md) - the safety invariant and how filing honors it.
- [`docs/ui.md`](docs/ui.md) - shell, views, controllers and widgets.
- [`docs/testing.md`](docs/testing.md) - pytest layout, coverage and UI smokes.
- [`docs/adr/README.md`](docs/adr/README.md) - architecture decision records.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) - development flow and standards.
- [`CHANGELOG.md`](CHANGELOG.md) - version history.

## License

MIT. See [`LICENSE`](LICENSE).
