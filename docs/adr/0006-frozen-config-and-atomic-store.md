# 6. Frozen config and atomic store

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

The worker reads folders, societies, `copy_files`, and `destination_template` on every PDF. The UI edits the same object when the user saves settings. A mutable config would let the worker observe a half-updated `societies` tuple, or file into a folder the UI already changed. A crash while writing `config.json` would leave the user with an empty file and no companies.

Config also has a history. 1.0.x wrote buying companies with a `name` field and, in Spanish exports, `nombre_fantasia`. The supplier registry, added later, uses `legal_name`. Those two spellings have to stay distinct so old `config.json` files still load.

## Decision

`AppConfig` and `SocietyMapping` in `src/automator/config/model.py` are Pydantic models with `model_config = ConfigDict(frozen=True)` (`SocietyMapping` also sets `populate_by_name=True`). A change is a new object. `SocietyMapping.name` stays `name` so JSON from 1.0.x loads without a migration. `trade_name` accepts the alias `nombre_fantasia` via `AliasChoices`. `Supplier.legal_name` in `domain/suppliers.py` is the registry field, stored as `razon_social` in SQLite.

`ConfigStore` in `src/automator/config/store.py` holds one snapshot behind a `threading.Lock`. `get()` returns that same frozen object. The UI and the engine both call `store.get` (`ConfigProvider`). `set` replaces the reference in memory. `update` writes disk first (`save_config`) and only then replaces the snapshot, so a failed save leaves memory aligned with what is on disk.

`save_config` writes `config.json.tmp`, `flush` + `os.fsync`, then `os.replace` onto `config.json`, then fsyncs the parent directory (skipped on Windows). `load_config` distinguishes a read `OSError` (lock, permissions) from invalid JSON or a `ValidationError`. A read error logs and returns `default_config()` without touching the file. Invalid content is renamed to `config.json.{YYYYMMDD-HHMMSS}.corrupt` and replaced in memory by the default. `load_store` persists that default when the path is missing.

Validators reject duplicate society CUITs, output folders inside the input folder, unknown destination-template tokens, and a `stability_timeout_s` outside 0..120.

## Consequences

`tests/config/test_config.py` can assign `snapshot.dry_run = True` and watch Pydantic raise, while `store.get().dry_run` stays false. The worker can hold a config for the duration of one `process` call and ignore a save that happens mid-file.

Users who still have a 1.0.x `config.json` keep their companies. A rename of `name` to `legal_name` would have forced a silent default on first launch, which would look like data loss.

Corruption recovery means a broken file becomes a timestamped backup plus a factory default (Downloads as input, `~/Automator/Facturas ordenadas` as base, no societies). The user has to re-enter companies. The alternative is refusing to start, which the packaged `.exe` handles poorly.

`ConfigStore.update` going to disk first means a UI save that fails on a network profile keeps showing the previous values after reload. That is the honest state.

## Alternatives considered

### Mutable AppConfig

In-place list edits are convenient for a settings form. They also let the worker iterate `societies` while the UI appends. Frozen models plus `tuple[SocietyMapping, ...]` make that race a type error.

### Write config.json in place

A single `write_text` is shorter. A power loss in the middle of that write is an empty config. The temp file, fsync, and `os.replace` are the durable path.

### Rename SocietyMapping.name to legal_name

That would match `Supplier`. It would also invalidate every 1.0.x `config.json` on `name`. The alias stays on `trade_name` (`nombre_fantasia`) for the same reason. The registry was new, so it could start with `legal_name`.
