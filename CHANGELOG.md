# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/); semantic versioning.

## [1.1.0] - 2026-08-19

### Added

- Filing policy lives in domain (`decide_filing`). Processor only orchestrates.
- Ledger schema versioning. Existing `history.db` files gain `issuer_cuit`.
- Duplicate detection is dual-read: historic identity or issuer CUIT plus number
  and type. A supplier rename no longer files a second copy.

### Changed

- UI split into shell, views and controllers. `main_window.py` is gone.
- Config, engine and parser are packages. Production files stay under 250 lines.
- Undo restores the file if marking the ledger fails.
- `open_folder` no longer creates a typed path that does not exist.
- PyInstaller `upx=False`. Inno Setup uses a stable AppId.

### Fixed

- Copy/dry-run ERROR is retried on rescan instead of being remembered as seen.
- Engine stop join timeout keeps the generation alive until threads actually die.
- SENTINEL is queued even if the watcher fails to stop.

## [1.0.1] - 2026-08-17

### Fixed

- Reprocessing a review file no longer creates a ` (n)` copy of itself.
- Retry pending now finds PDFs nested under `_PARA_REVISAR/{supplier}/`.
- History clear action is labeled "Vaciar historial".


### Added

- Copy mode (copy instead of move): copies each invoice to its destination and
  leaves the original in the input folder, tracking processed sources in the
  history to avoid reprocessing.

### Changed

- History view: fixed the clipped heading, introduced a clear button hierarchy
  (brand-color primary, dark secondary, ghost tertiary), disabled actions that
  are not available (nothing to undo, nothing pending), and added toolbar icons.
- Rewrote the README in English and translated the documentation and code
  comments to English.

## [1.0.0] - 2026-08-14

### Added

- Desktop application (CustomTkinter) that classifies and files AFIP invoices by
  company (CUIT), replacing the original single-piece script.
- Detection of voucher type/letter by AFIP code, number, supplier, buyer CUIT
  and issue date.
- Safe routing: unclassified, review, quarantine and duplicates, with the
  principle of never filing incorrectly in silence.
- Persistent audit history in SQLite, with undo of the last move and retry of
  pending items.
- Duplicate detection by identity (supplier, number, type).
- Configurable folder structure with a template (supplier, year, month, day).
- First-run wizard and optional system notifications.
- Persistent pending notice read from the folders.
- Validated, immutable configuration, with atomic save and recovery from
  corruption.
- Brand icon, packaging with PyInstaller and a Windows installer (Inno Setup).
- Tooling: ruff, strict mypy, pytest, pre-commit and CI on GitHub Actions.

### Notes

- The application ships with no company or CUIT preloaded: everything is
  configured from the interface.
