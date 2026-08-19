# Concurrency

The engine runs on background threads. The Tkinter thread only starts, stops and paints. Communication is a `queue.Queue` of `EngineEvent` values plus a `UiMailbox` of callbacks, both drained from `EngineBridge.poll_events` every `_POLL_MS` (150 ms). Tkinter is not thread-safe: widgets are touched only on that poll.

## Generations

A generation is one start of `ProcessingEngine`. `_launch` in `services/engine/lifecycle.py` increments `_generation_id`, replaces `_queue` with a new `queue.Queue`, replaces `_stop_event` with a new `threading.Event`, then `Inbox.clear()` and `SourceMemory.clear()`. An old worker that is slow to finish still holds the previous queue and stop signal. Halt puts `SENTINEL` on the captured queue, so that worker exits without sharing the new one.

`_emit` stamps `generation_id` on every event that still has `0`. `EngineBridge` records the id from `STARTED` and drops later events whose id differs, so a late result from generation 1 cannot paint the generation 2 monitor. `STARTED` itself always applies and resets session stats.

`_claim_start` rejects a start while `_starting` is set or `_worker` / `_rescanner` are still assigned. `_lifecycle_lock` serializes `start` and `stop`. A start that fails after threads were created calls `halt` then `join_threads`; if the join succeeds, the references are cleared and `is_running` is false.

## Watcher, worker and rescanner

`WatcherFactory` is `Callable[[Path, Callable[[Path], None]], FolderWatcher]`. The default is `FolderWatcher` in `services/watcher.py`, a watchdog `Observer` on the input folder (non-recursive) that notifies on create and on move-to-PDF (browsers that download to a temp name). `_OBSERVER_JOIN_TIMEOUT_S` is 5 seconds on stop.

`_launch` assigns threads incrementally: `self._watcher = start_watcher(...)`, then `self._worker = start_worker(...)`, then `self._rescanner = start_rescanner(...)`. `start_worker` is a daemon thread named `automator-worker` running `Worker.run`. `start_rescanner` is a daemon thread named `automator-rescan` that waits `RESCAN_INTERVAL_S` (60 s) on the stop event and calls `Inbox.rescan`.

`halt` sets the stop event, stops the watcher, and puts `SENTINEL` on the work queue. `join_threads` waits `WORKER_JOIN_TIMEOUT_S` (10 s) on worker and rescanner. Both dead means the generation is clear. A timeout logs, emits `ERROR` with `El monitor no pudo detenerse a tiempo.`, and leaves the thread references so the next start stays rejected until they die.

`is_running` is true while `_worker` or `_rescanner` is set. `stop` emits `STOPPED` only after a successful join. `EngineBridge` treats `STOPPED` as idle, then calls `start` again when settings asked for a restart via `consume_restart()`.

## Inbox reservation

`Inbox` owns `_inflight`, a set of `path_key` values (`os.path.abspath`). `reserve` adds the key under the shared lock and returns false when it is already present. `release` discards it. `enqueue` skips `SourceMemory.already_processed`, then reserves, emits `DETECTED`, and puts the path on the current queue. `requeue` is the same without the detect event, used by rescan and retry.

`process_existing` lists PDFs in the input folder and enqueues each. `rescan` does the same through `requeue`, and emits a single `ERROR` the first time the folder is unreadable (`_input_unreadable`). `reprocess_pending` lists PDFs recursively in `review_folder` and `quarantine_folder` so nested `{supplier}` subfolders are retried.

`Worker.safe_process` always `release`s in `finally`, so a file that errors is dropped from `_inflight` as well.

## Source memory

`SourceMemory` remembers sources that stay in the input folder (copy mode and dry-run). `_COPY_PLACED` is `MOVED`, `UNCLASSIFIED`, `DUPLICATE`, `NEEDS_REVIEW`, `QUARANTINED`. `_REMEMBERED` adds `DRY_RUN`. After a remembered outcome, that path's `file_signature` (`abspath|size|mtime`) is stored in `_seen_signatures`. Copy mode also calls `Ledger.mark_source_seen`.

`already_processed` checks the in-memory set first. In copy mode it then asks `Ledger.source_seen`, which requires the dest file to still exist (see `docs/persistence.md`). A generation start clears the in-memory set; the ledger still covers copy-mode files across restarts.

## Events and the Tk thread

`EngineEventType` is `started`, `stopped`, `detected`, `result`, `error`. `emit` swallows sink failures so a UI bug cannot kill the worker. `MainWindow` passes `self._events.put` as the sink and constructs `EngineBridge` with that same queue.

`EngineBridge.poll_events` returns immediately when `suspend()` was called (window close). Otherwise it `_drain`s the engine queue, drains `UiMailbox`, and reschedules itself with `widget.after(150, ...)`. `_handle_event` applies the generation filter, updates running state, increments session counters, and appends the activity log. `SKIPPED_MISSING` is ignored. A path-less `ERROR` shows a messagebox and restores the toggle from `engine.is_running`.

`UiMailbox` is a `queue.Queue` of zero-argument callbacks. Background work that must touch widgets (`run_async` helpers, retry confirmations, settings) `post`s a lambda; only `drain` on the Tk thread runs it. `run_async` starts a daemon thread, which is how `EngineBridge.start` / `stop` call `ProcessingEngine` without blocking the UI.

`PendingController` polls review and quarantine counts every `_PENDING_POLL_MS` (5000 ms) off the Tk thread, then publishes the pair through `_latest` so `_flush` applies it on the next poll.

## Ledger requirement and process_now

`open_ledger` in `ui/backend.py` returns `None` on `OSError` or `sqlite3.Error`. `EngineBridge.require_ledger` records that flag. `start` shows `No se pudo abrir el historial...` and returns when the ledger is missing, because duplicates and undo both need it. Settings are saved through `collect_and_save` before the async `engine.start`.

`ProcessingEngine.process_now` is the synchronous path used by tests and by a one-shot process. It `Inbox.reserve`s, runs `Worker.process_now` (processor, `record_result`, `memory.remember`, `RESULT` event), then `release`s in `finally` so a direct call still participates in inflight tracking. History retry uses `reprocess_pending` plus the worker queue.
