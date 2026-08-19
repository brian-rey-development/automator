# Invariant

No invoice is ever misfiled or lost silently. On uncertainty the file goes to `_PARA_REVISAR` or `_ERRORES`, and a ledger row is written. A guessed buyer or supplier is a review, a quarantine, or an unclassified archive. `MOVED` is reserved for an exact buyer CUIT on a reliable, new invoice.

## Filing policy

`InvoiceProcessor.process` in `services/processing/processor.py` is the orchestration. A missing path returns `SKIPPED_MISSING`. When `wait_for_stability` is on, `wait_until_stable` must see a constant size within `stability_timeout_s`; a download that keeps growing is quarantined. Text comes from `extract_text`; a reader exception or a blank PDF is quarantined. `parse_invoice` then `resolve_buyer`, then `_canonicalize_supplier` against `SupplierRegistry.match` (buyer CUIT excluded).

`decide_filing` in `domain/filing/decision.py` is the only policy. Order: ambiguous buyer to `NEEDS_REVIEW`; `is_reliable` false to `NEEDS_REVIEW`; duplicate to `DUPLICATE`; fuzzy buyer to `NEEDS_REVIEW`; no buyer CUIT to `UNCLASSIFIED`; else `MOVED`. Reliability (`domain/filing/reliability.py`) requires `has_number` and `has_supplier`, and rejects a supplier whose normalized name equals one of the configured company `match_names()`. An invoice that looks like it was issued by our own society goes to review.

Fuzzy buyer matches (`_FUZZY_THRESHOLD` 0.90, `_FUZZY_MARGIN` 0.05) return a candidate CUIT with `fuzzy=True`. `decide_filing` still chooses `folders.review` and the message `Emparejada por nombre ({percent}%): se envio a revision para confirmar la compradora.` The destination for that candidate is `_PARA_REVISAR`.

Leftover CUITs after subtracting the buyer skip the registry name fallback (`SupplierRegistry.match`). An unknown or colliding issuer CUIT cannot be claimed by a known alias on the page. When that leaves `has_supplier` false, or the number missing, `is_reliable` fails and the file lands in `_PARA_REVISAR`. Unique leftover CUITs that hit the registry canonicalize `legal_name` and `issuer_cuit` and may file.

## Outcomes

**Moved.** Exact buyer CUIT, reliable invoice, new identity. `archive_base` chooses the society folder (`folder_for_cuit`) or the orders tree (`orders_base_for`). `destination_dir` applies `destination_template` (default `{supplier}`). `place_file` moves or copies under that directory with `build_filename`. Message: `Archivado correctamente.`

**Unclassified.** Reliable invoice whose buyer CUIT is unknown and whose name was below the fuzzy threshold. The PDF is still archived, under `_SIN_CLASIFICAR` (or `_SIN_SOCIEDAD` for orders), so it is findable. Outcome is `UNCLASSIFIED`, which is a `FILED_OUTCOMES` member: later copies of the same identity are duplicates. Message: `Archivado sin clasificar: no se detecto la sociedad compradora.`

**Duplicate.** `Worker.is_archived_duplicate` asks `Ledger.archived_destination` for `identity` and, when present, the exact `issuer_identity` `{issuer_cuit}|{number}|{type}`. Only unreverted `MOVED` / `UNCLASSIFIED` rows count, and the previous dest file must still exist. The new PDF goes to `_DUPLICADOS`. A deleted original is filed again rather than diverted as a phantom duplicate.

**Review.** Incomplete data, ambiguous buyer, fuzzy buyer, unknown supplier, or supplier equal to a configured company. Destination is `config.review_folder` (`_PARA_REVISAR`) plus the template subfolder. The source is moved (or copied from the inbox) so the input folder stays empty of doubtful files.

**Quarantine.** Unreadable PDF, unstable download, extractor failure, or a failed archive. `_quarantine` places the original name in `quarantine_folder` (`_ERRORES`). A failed quarantine leaves the file in the input folder as `ERROR` so the next rescan retries it. Dry-run reports `ERROR` without moving.

**Skipped missing.** The path disappeared before process. No ledger row.

## Placement and copies

`place_file` calls `file_ops.copy_file` or `move_file`. Both go through `_transfer`: create the directory, skip when source and dest are already the same file, otherwise `unique_destination` which appends ` (2)`, ` (3)`, ... so a name collision keeps both files. `shutil.move` / `shutil.copy2` receive Windows long-path or `\\?\UNC\` forms from `_os_path`.

Copy mode (`AppConfig.copy_files`) copies from the input folder and leaves the original. `_copy_inbox_only` turns copy off when the source already sits under `review_folder` or `quarantine_folder`, so retry moves those files out. A review copy that stayed would loop forever on rescan. `SourceMemory` plus `Ledger.source_seen` (dest must still exist) stop the watcher from re-copying an inbox original.

## Ledger and undo

`Worker.record_result` writes every result except `SKIPPED_MISSING`, including review, quarantine, duplicate and error. A ledger failure is logged; processing continues, but the next start still requires an open ledger (`EngineBridge.require_ledger`) so duplicate detection and undo stay available.

`perform_undo` in `services/undo.py` moves the dest file back to the input folder, then `mark_reverted`. `mark_reverted` also deletes `processed_sources` for that `source_signature`, which is how copy-mode undo forgets the original. If the mark fails, the file is moved back to the archived path. A missing dest still marks reverted (`UndoOutcome.MISSING`) so the row cannot be undone twice. `HistoryActions.undo_last` runs only while the monitor is stopped, using `last_undoable` (which includes review and quarantine).

## Pending review and retry

`PendingController` counts PDFs recursively in `_PARA_REVISAR` and `_ERRORES` every 5 seconds, off the Tk thread. `MonitorView.set_pending(review, quarantine)` shows those counts separately (`N para revisar`, `M en cuarentena`). `open_review` opens the folder that has files: quarantine only opens quarantine, both open both, otherwise review. A rising total can fire `notify` when `AppConfig.notify` is on.

`HistoryActions.reprocess_pending` requeues those folders. If the engine is already running it calls `ProcessingEngine.reprocess_pending` immediately. If it is stopped, it saves settings, sets `_retry_when_started`, and calls `EngineBridge.start`. `STARTED` fires `on_engine_started`, which then requeues. Retry therefore always goes through a live generation with a current config and a reserved inbox, and copy-under-review still forces a move so the pending folders drain.
