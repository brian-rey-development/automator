# Persistence

On-disk state lives in three places resolved by `paths.py`: `config.json` for companies and folders, `history.db` for the audit ledger and the supplier table, and a rotating `automator.log`. Writes are atomic or WAL-backed so a crash leaves a readable previous version rather than a half-written file.

## Platform paths

`APP_NAME` is `Automator` and `APP_AUTHOR` is `Brian Rey`. `config_path()` is `platformdirs.user_config_dir` plus `config.json`. `ledger_path()` is `user_data_dir` plus `history.db`. `log_dir()` is `user_log_dir`. `assets_dir()` is `sys._MEIPASS/assets` inside a frozen PyInstaller build, and the repository `assets/` folder when running from source.

## Configuration

`load_config` in `config/store.py` returns `default_config()` when the file is missing. A read `OSError` (lock, permissions, network drive) also returns the default and leaves the file in place. Invalid JSON or a `ValidationError` is treated as corruption: the file is renamed to `config.json.{YYYYMMDD-HHMMSS}.corrupt` and the default is used.

`save_config` writes a sibling `.tmp`, flushes, `fsync`s the file, then `os.replace`s onto `config.json`. On non-Windows it also `fsync`s the parent directory so the rename survives a crash. `ConfigStore` holds one frozen `AppConfig` behind a lock. `get()` returns that snapshot. `update()` saves to disk first, then replaces the in-memory reference, so a failed save keeps the previous snapshot. `load_store` writes the default file when none exists yet.

`AppConfig` and `SocietyMapping` are frozen Pydantic models. Review and duplicates folders are derived (`base/_PARA_REVISAR`, `base/_DUPLICADOS`); quarantine is a stored path, defaulting to `base/_ERRORES`.

## SQLite and schema versions

`connect_wal` in `services/persistence/sqlite.py` opens `history.db` with `check_same_thread=False`, a 30 second busy timeout, `row_factory=sqlite3.Row`, `PRAGMA journal_mode=WAL` and `PRAGMA synchronous=NORMAL`. The same helper is used by `Ledger` and `SupplierStore`.

`Ledger` creates the base tables, then `apply_migrations`. `records` starts with `id`, `ts`, `source_name`, `identity`, `supplier`, `voucher`, `outcome`, `destination`, `message` and `reverted`. `processed_sources` is `(signature PRIMARY KEY, ts)` for copy-mode source memory. `schema_version` tracks the integer version.

Migrations in `services/persistence/migrations.py` are additive. Version 1 stamps an existing `records` table. Version 2 adds `issuer_cuit` and `idx_records_issuer_cuit`. Version 3 (current) adds `issuer_identity` and `source_signature`, plus indexes on both. Columns already present are skipped via `PRAGMA table_info`, so a database created at v3 still records version 3.

## Ledger

Every `ProcessResult` except `SKIPPED_MISSING` is inserted by `Ledger.record`, including review, quarantine, duplicate and error. The row stores `identity`, `issuer_cuit`, `issuer_identity` and `file_signature(result.source)` when those values exist.

`archived_destination(identity, issuer_cuit=None)` looks at unreverted `FILED_OUTCOMES` (`moved`, `unclassified`) that have a destination. It matches `identity` exactly and, when `issuer_cuit` is passed, also matches `issuer_identity` as `{issuer_cuit}|{number}|{type}` taken from the identity suffix. The latest hit wins. `is_archived_duplicate` in `services/engine/worker.py` further requires that destination path to still exist, so a removed original is filed again rather than treated as a phantom duplicate.

`last_undoable` returns the latest unreverted row whose outcome is in `UNDOABLE_OUTCOMES` and whose destination is set. That includes `needs_review` and `quarantined`, so the history toolbar can return a review or quarantine file.

`mark_reverted` sets `reverted = 1` and deletes that row's `source_signature` from `processed_sources`. Copy-mode undo therefore forgets the original so the watcher can pick it up again.

`source_seen(signature)` reads the latest unreverted `records` row with that `source_signature`. It is true only when `destination` is set and `path_exists` confirms the dest file. Missing dest means the source is eligible again. Rows that predate version 3 fall back to `_legacy_source_seen` on the `processed_sources` table. `mark_source_seen` is `INSERT OR IGNORE` into that table; `SourceMemory` calls it for copy-mode placements.

`recent(limit=200)` feeds the history view. `clear()` deletes both `records` and `processed_sources`. All ledger methods take the instance lock.

## Supplier store

`SupplierStore` lives in the same `history.db`. The `suppliers` table is `cuit` (primary key), `razon_social`, `nombre_fantasia` and `aliases` (JSON array of extra aliases). `bulk_upsert` loads by CUIT, runs `merge_supplier`, and `INSERT OR REPLACE`s. `all()` maps those Spanish columns back to `Supplier(legal_name=..., trade_name=...)`.

`SupplierRegistryStore` holds the immutable `SupplierRegistry` snapshot the worker reads. `get()` returns the current snapshot. `reload()` rebuilds from `store.all()` after an import or edit. The worker reads that snapshot on the hot path. `ui/backend.py` opens ledger and supplier store on the same `ledger_path()` and continues with `None` if either open fails.

## Logs

`setup_logging` in `logging_config.py` writes `automator.log` under `log_dir()`, rotated at `_MAX_BYTES` (1_000_000) with `_BACKUP_COUNT` (5). Format is `%(asctime)s [%(levelname)s] %(name)s: %(message)s`. A stream handler is attached only when `sys.stderr` is set; the windowed `.exe` has no console, and logging still reaches the file. `log_location()` is the path shown to the user after a failure.
