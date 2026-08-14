# Changelog

All notable changes to this project. Format based on
[Keep a Changelog](https://keepachangelog.com/); semantic versioning.

## [Unreleased]

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
