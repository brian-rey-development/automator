# 5. Engine generations

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

The engine watches the input folder, processes PDFs on a background thread, and tells the UI what happened. CustomTkinter (Tkinter) is not thread-safe. The user can start, stop, and restart the monitor, and can save settings that stop and start again. A worker from generation 1 that still holds generation 2's queue will process files the new UI session has already forgotten, or will paint widgets from the wrong thread if anyone takes a shortcut.

Stop also has to be honest. A failed start that leaves an orphan worker, or a start that replaces the queue while the old worker is still draining it, loses invoices or double-files them.

## Decision

Each `ProcessingEngine.start` is a generation. `ProcessingEngine._launch` in `src/automator/services/engine/lifecycle.py` increments `_generation_id`, then assigns a fresh `queue.Queue` and a fresh `threading.Event` stop signal. `Inbox.clear` and `SourceMemory.clear` run on the same launch so in-flight keys and seen signatures from the previous generation die with it.

Threads are created through `src/automator/services/engine/runtime.py`. `start_watcher` builds a `FolderWatcher` on `config.input_folder`. `start_worker` starts `Worker.run` as daemon thread `automator-worker`. `start_rescanner` starts `_rescan_loop` as `automator-rescan` (wake every `RESCAN_INTERVAL_S` = 60s). Assignment is incremental: `_watcher`, then `_worker`, then `_rescanner`. If `start_rescanner` raises, the worker reference is already stored, so `_cleanup_failed_start` can `halt` it.

`halt` sets the stop event, stops the watcher, and puts `SENTINEL` on that generation's queue. `join_threads` waits `WORKER_JOIN_TIMEOUT_S` (10s). If a join times out, `_clear_if_stopped` keeps the worker and rescanner references. `is_running` stays true (`_worker is not None or _rescanner is not None`), `_claim_start` rejects another start, and a later `stop` can still join the same threads. That is the rule behind `test_failed_start_join_timeout_keeps_refs`.

The engine talks to the UI only through `EngineEvent` (`engine/events.py`: `STARTED`, `STOPPED`, `DETECTED`, `RESULT`, `ERROR`). Each event is stamped with `generation_id`. `emit` swallows sink exceptions so a broken UI callback cannot kill the worker.

`EngineBridge.poll_events` in `src/automator/ui/controllers/engine_bridge.py` is the only consumer. It drains the event queue and `UiMailbox` on the Tk thread, every `_POLL_MS` (150ms), via `widget.after`. Events whose `generation_id` is set and differs from the `STARTED` generation are dropped. Widgets are touched only there.

## Consequences

Start/stop tests in `tests/services/test_engine.py` can assert generation ids `1` then `2` on successive `STARTED` events, and can assert that a failed watcher factory leaves `is_running` false. A sink that raises still returns `MOVED` from `process_now`.

The UI stays a poller. Controllers post work with `system_utils.run_async` (start, stop, Excel import, retry) and come back through the mailbox or the event queue.

Operators live with a 10s join budget. A stuck worker blocks a clean restart until it dies or the process exits. That is preferred to leaking a worker onto a new queue.

Rescan is a safety net for events watchdog missed. Combined with copy-mode source signatures (ADR 0008), it will see the original PDF again and skip it when it was already placed.

## Alternatives considered

### One queue for the life of the process

Reusing the queue across start/stop is simpler. An old worker that missed `SENTINEL` would then drain files meant for the next generation. Recreating the queue and the stop event on every start makes that mix-up impossible.

### Worker calling `widget.after` or updating labels directly

That is the usual Tk shortcut. It races with the main loop and crashes on some platforms. The event queue plus a 150ms poll is slower to paint, and it is the only legal path onto the Tk thread.

### Killing threads on stop

There is no safe thread kill in CPython that leaves a half-moved PDF consistent. Join with a timeout, keep refs on failure, and refuse a new start until the old generation is gone.
