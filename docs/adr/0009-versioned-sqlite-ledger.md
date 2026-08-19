# 9. Versioned SQLite ledger

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

Every processed PDF leaves an audit row the History view can show after a restart. Duplicate detection (ADR 0004) and copy-mode memory (ADR 0008) read that same store. Suppliers can number in the hundreds, so they cannot live in `config.json` next to a handful of buying companies.

The app is a desktop `.exe`. There is no DBA. A schema change has to open an old `history.db` and keep every row the user already has. Concurrent UI reads (history table, pending counts) and worker writes (record after each file) happen in one process, two threads.

## Decision

History lives at `paths.ledger_path()` (`<user_data>/history.db`). Connections go through `connect_wal` in `src/automator/services/persistence/sqlite.py`: `sqlite3.connect(..., check_same_thread=False, timeout=30)`, `row_factory = sqlite3.Row`, `PRAGMA journal_mode=WAL`, `PRAGMA synchronous=NORMAL`.

`Ledger` in `src/automator/services/ledger.py` creates `records` and `processed_sources`, then calls `apply_migrations`. Migrations in `persistence/migrations.py` are additive. Existing columns and rows stay in place. `schema_version` holds the integer version.

Version 1 is the baseline (`schema_version` row after the original `records` table). Version 2 adds `records.issuer_cuit` and `idx_records_issuer_cuit`. Version 3 (`_CURRENT = 3`) adds `records.issuer_identity` and `records.source_signature`, plus indexes on both. `_add_column` is idempotent (`PRAGMA table_info`). Opening a pre-column database in tests yields version 3 with the new columns present.

The supplier registry is table `suppliers` in the same file (`SupplierStore` in `supplier_store.py`): `cuit` primary key, `razon_social`, `nombre_fantasia`, `aliases` as a JSON list. `SupplierRegistryStore` loads `store.all()` into an immutable `SupplierRegistry` and exposes `get()`. The worker receives `registry_provider=registry.get` and reads that snapshot only. Imports and edits call `reload()` after `bulk_upsert` / `delete` / `clear`, the same snapshot pattern as `ConfigStore`.

`ui/backend.py` opens both stores on that one path and closes them on a clean shutdown.

## Consequences

`tests/services/test_ledger.py` can build a legacy `records` table without `issuer_cuit` and assert the column appears. Duplicate lookup and undo keep working across upgrades.

WAL lets the worker `INSERT` while the History view `SELECT`s `recent(200)`. `synchronous=NORMAL` is a crash-window trade for desktop latency. A power loss can lose the last few WAL frames. The invariant still holds for files already on disk. The missing piece would be a ledger row, which retry or a later duplicate check can rebuild.

One file means one backup, one `close()`, and one Windows file lock. A corrupt `history.db` takes suppliers down with history. `open_ledger` / `open_supplier_store` catch `OSError` and `sqlite3.Error` and continue without that store. Duplicate detection then pauses (`EngineBridge.require_ledger`).

The worker's registry snapshot can be a few seconds behind an import that has not yet called `reload`. `SuppliersController` reloads before it refreshes the table, so the next `process` sees the new snapshot.

## Alternatives considered

### JSON history next to config.json

A JSON array is easy to diff. Concurrent appends from the worker and a UI clear would need the same atomic-replace dance as config, without indexes for `identity` and `issuer_identity`. SQLite WAL is the concurrent log.

### Destructive schema upgrades

`DROP TABLE records` on version mismatch would make installs simple. It would also wipe the only duplicate memory the user has. Additive `ALTER TABLE` plus `schema_version` keeps old rows.

### A separate suppliers.db

A second database would isolate a registry rebuild from audit history. It would also double WAL files, close paths, and Windows locks. Hundreds of suppliers are small. They share `history.db` and stay off the worker's query path via `SupplierRegistry`.
