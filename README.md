# Automator - AFIP invoice classifier

Author: Brian Rey

Desktop application that watches a downloads folder, reads every invoice PDF,
detects the voucher type, its number, the supplier and the buying company (by
CUIT), and files the renamed PDF into the right folder.

It replaces the original single-file script with a full application: a modern
graphical interface, persistent configuration, robust error handling and a test
suite.

It ships with no company or CUIT preloaded: everything is configured from the
interface. On first launch, a wizard helps you set up the minimum needed.

## Guiding principle

**No invoice is ever misfiled or lost silently.** On any uncertainty (supplier
not detected, ambiguous buyer, unreadable PDF) the file goes to review or
quarantine, never to a guessed destination. Every change must preserve this
invariant.

## Features

- Modern interface (CustomTkinter) designed to be used with no prior experience:
  clear labels, help text, folder pickers and a first-run wizard that guides the
  initial setup.
- Voucher type and letter detection by AFIP code, with a text-based fallback.
- Routing by CUIT to each company folder, configurable from the interface.
- Configurable folder structure via a template (by supplier and, optionally, by
  the year and month of the issue date).
- Persistent audit history (SQLite): everything processed is recorded and
  survives a restart. Includes undo of the last move and retry of pending files
  after adjusting the configuration.
- Duplicate detection: an already-filed invoice (same supplier, number and type)
  goes to `_DUPLICADOS` instead of being filed twice.
- Automatic "to review" folder when extraction is not reliable or several of your
  own companies appear, so nothing is misfiled without anyone noticing.
- Persistent pending notice read from the folders, with an optional system
  notification when new ones appear.
- Processes whatever was already in the folder on startup and periodically
  retries files that were left pending.
- Waits for the download to finish before moving (avoids half-downloaded files).
- No overwrites: if the name already exists, it appends ` (2)`, ` (3)`, etc.
- Automatic quarantine of unreadable or failing PDFs, without stopping the monitor.
- Validated, immutable configuration, saved atomically and with recovery if the
  file gets corrupted (it can never leave the app unable to open).
- Dry-run mode to preview what it would do without moving anything, and rotating logs.

## Requirements

- Python 3.11 or newer.
- Windows for the final executable (the code also runs on macOS and Linux).

## Development usage

With `make` (recommended):

```bash
make install   # creates the virtual environment and installs everything
make run       # runs the application
make demo      # generates sample invoices and opens the app to try it
make check     # linting + types + tests
```

`make demo` creates sample PDFs in the configured input folder covering every
case (filed by company, unclassified, to review and quarantine). When the app
opens, press "Iniciar" to watch them being processed in real time.

Without `make`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m automator
```

On macOS or Linux the equivalent is `python3 -m venv .venv && source .venv/bin/activate`.
`uv` is not required; if you have it, `uv pip install -e ".[dev]"` works too.

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
(`assets\automator.ico`) first.

### Installer (optional)

With [Inno Setup](https://jrsoftware.org/isinfo.php) installed, build the
installer with a start-menu shortcut and an auto-start option:

```powershell
iscc installer\automator.iss
```

It lands in `dist\installer\Automator-Setup-1.0.0.exe`.

## Quality

```bash
ruff check .      # linting (fast)
ruff format .     # formatting
mypy              # strict types
pytest            # tests with core coverage
```

Continuous integration runs the exact same commands on Python 3.11, 3.12 and 3.13
(UI smoke tests run under xvfb), plus a Windows job that builds the executable on
every push. Core coverage has an 80% floor enforced in CI.

## Architecture

The project separates the pure core (no side effects, 100% testable) from the
services that do input/output and from the interface.

```
src/automator/
  domain/      Models, parser, naming and classification (pure logic)
  services/    PDF reading, file IO, watcher and processing engine
  ui/          Desktop interface (CustomTkinter)
  config.py    Validated configuration model and persistence
tests/         Core and services test suite
```

The engine runs on a background thread and talks to the interface through an
event queue, respecting the fact that Tkinter is not thread-safe.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) - layers, concurrency and flow.
- [`docs/features.md`](docs/features.md) - features in detail.
- [`docs/configuration.md`](docs/configuration.md) - fields and the folder template.
- [`CONTRIBUTING.md`](CONTRIBUTING.md) - development flow and standards.
- [`CHANGELOG.md`](CHANGELOG.md) - version history.

## License

MIT. See [`LICENSE`](LICENSE).
</content>
</invoke>
