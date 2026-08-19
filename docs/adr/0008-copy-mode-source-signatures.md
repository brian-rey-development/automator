# 8. Copy mode source signatures

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

Default filing uses `shutil.move`. The PDF leaves the input folder, so a later rescan cannot see it. Some users want the original to stay in Downloads (or whichever inbox they chose) and a filed copy under `base/{empresa}/{proveedor}`. Copy mode (`AppConfig.copy_files`) does that.

Once the original stays, the watcher and the 60s rescanner will see it again. Without memory, the engine would copy it forever, or treat the second sighting as a voucher duplicate even when it is the same file. Undo has the opposite problem. After the filed copy is moved back to the inbox, the original (or the returned copy) has to be eligible again.

Retry from `_PARA_REVISAR` and `_ERRORES` has a third wrinkle. If copy mode still copied, retry would leave the uncertain file in review and write a second copy elsewhere. Retry has to relocate.

## Decision

`place_file` in `src/automator/services/processing/placement.py` calls `file_ops.copy_file` (`shutil.copy2`) when `copy_files` is true, otherwise `file_ops.move_file` (`shutil.move`). Both go through `unique_destination`, which appends ` (n)` on collision, and through `_os_path` (Windows `\\?\` and `\\?\UNC\` prefixes).

The stable source id is `file_signature` in `file_ops.py`: `abspath|st_size|int(st_mtime)`. `Ledger.record` stores it as `records.source_signature` (schema v3). `SourceMemory.remember` also writes `processed_sources` via `mark_source_seen` for outcomes in `_COPY_PLACED` (`MOVED`, `UNCLASSIFIED`, `DUPLICATE`, `NEEDS_REVIEW`, `QUARANTINED`).

`Ledger.source_seen` prefers the latest non-reverted `records` row with that signature. It returns true only when `destination` is set and `path_exists(destination)`. Missing dest means the copy is gone, so the original may be processed again. If no row exists, it falls back to `_legacy_source_seen` on the `processed_sources` table (pre-v3 rows).

`Ledger.mark_reverted` sets `reverted = 1` and `DELETE`s that signature from `processed_sources`. Copy-mode undo (`perform_undo` then `mark_reverted`) therefore forgets the source, and the inbox file can be filed again.

`InvoiceProcessor` forces copy off when the source already sits under `config.review_folder` or `config.quarantine_folder` (`_copy_inbox_only`). Retry then moves the PDF out of review or quarantine for real. Inbox copies still use `copy2`.

`ERROR` and `SKIPPED_MISSING` are left out of `_COPY_PLACED`, so a failed place is retried on the next scan (`test_copy_mode_retries_error_outcome`).

## Consequences

`tests/services/test_engine.py` asserts that after a copy-mode `MOVED`, `process_existing` emits no `DETECTED`. The original PDF is still in the input folder. Dry-run uses the in-memory seen set the same way, without writing `processed_sources`.

Users who empty a destination folder (or undo) get another chance. Users who leave the filed copy in place keep a quiet inbox.

Signatures include size and mtime, so a re-download that overwrites the same path with new bytes is a new file. A touch that only updates mtime is also a new file, and may copy again. That is accepted. Path-only identity would miss the overwrite.

Retry from review in copy mode becomes a move. The inbox original, if it still exists from the first copy, remains covered by `source_seen` until undo or a missing destination.

## Alternatives considered

### Re-copy on every rescan

That would need no extra tables. The inbox would spawn a new ` (n)` file every 60 seconds. Source signatures exist so copy mode is usable as a daily watcher.

### Path-only identity

`abspath` alone is stable across a completed download. It also treats a replaced PDF at the same path as already done. Size and mtime catch the replacement. The cost is a possible recopy after a `touch`.

### Honor copy_files for review and quarantine too

A consistent flag is easier to explain. Retry would then copy out of `_PARA_REVISAR` and leave the uncertain original there, so the pending count never drops. `_copy_inbox_only` is the exception that makes "Reintentar" relocate.
