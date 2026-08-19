# Testing

The suite follows the same three layers as the code. `make check` is the
gate before a commit: lint, format, types, tests with coverage, import
contracts and the production file-size budget.

## Quality gate

`make check` runs, in order:

| Step | Command | What it enforces |
|---|---|---|
| lint | `ruff check .` | Style and bug rules from `pyproject.toml` |
| format-check | `ruff format --check .` | Formatting only, no writes |
| typecheck | `mypy` | `mypy --strict` on `src/automator` |
| cov | `pytest --cov` | Tests plus the coverage floor |
| import-lint | `PYTHONPATH=src lint-imports` | Layer contracts |
| file-size | `python scripts/check_file_size.py` | 200-line production modules |

CI (`.github/workflows/ci.yml`) runs the same tools on Python 3.11, 3.12
and 3.13, with `xvfb-run -a pytest --cov` so UI smokes have a display.

pytest is configured in `pyproject.toml`: `testpaths = ["tests"]`,
`pythonpath = ["src", "tests"]`, `--strict-markers`, `--timeout=30`.

## Layout

Tests live next to the layer they cover.

| Path | Covers |
|---|---|
| `tests/domain/test_filing.py` | `decide_filing`, `is_reliable` |
| `tests/domain/test_buyer.py` | Exact CUIT then guarded fuzzy match |
| `tests/domain/test_parser.py` | AFIP text extraction |
| `tests/domain/test_destination.py` | Folder template tokens |
| `tests/domain/test_filenames.py` | Sanitized destination names |
| `tests/domain/test_models.py` | Identity, presence flags |
| `tests/domain/test_cuit.py` | Normalize and check digit |
| `tests/domain/test_names.py` | `normalize_name` |
| `tests/domain/test_suppliers.py` | Registry matching |
| `tests/services/test_processor.py` | `InvoiceProcessor` placement |
| `tests/services/test_engine.py` | Generations, queue, worker |
| `tests/services/test_ledger.py` | SQLite history and duplicates |
| `tests/services/test_undo.py` | Move back and mark reverted |
| `tests/services/test_file_ops.py` | Move, copy, unique names, Windows paths |
| `tests/services/test_watcher.py` | Folder events |
| `tests/services/test_pdf_reader.py` | Text extraction fallbacks |
| `tests/services/test_excel_import.py` | Society and supplier workbooks |
| `tests/services/test_supplier_store.py` | SQLite registry snapshot |
| `tests/config/test_config.py` | `AppConfig`, store, validation |
| `tests/ui/test_main_window.py` | Window smoke: nav, forms, wiring |
| `tests/ui/test_outcomes.py` | `presentation` helpers |

## Shared fixtures

`tests/conftest.py` gives every layer a disposable `AppConfig`.
`make_config(**overrides)` points input, output, unclassified, quarantine
and orders at `tmp_path`, seeds one buyer (`CUIT_ONE` / `COMPRADORA UNO SA`)
and turns `wait_for_stability` off so dummy files skip the poll interval.
`dummy_pdf(name)` writes a tiny `%PDF` into the input folder.

Sample texts and CUITs live in `tests/fixtures/invoices.py`
(`FACTURA_A_TEXT`, `ORDEN_COMPRA_TEXT`, `NO_RAZON_SOCIAL_TEXT`, ...).
Parser and processor tests import those constants instead of inventing
new blobs inline, unless the case is a one-line variant.

## Decision branches

These outcomes stay covered at both policy and placement:

| Outcome | Domain | Processor |
|---|---|---|
| Moved | `test_known_buyer_is_moved` | `test_moves_invoice_to_matching_society_folder` |
| Unclassified | `test_unknown_buyer_is_unclassified` | `test_unknown_cuit_goes_to_unclassified_folder` |
| Duplicate | `test_duplicate_goes_to_duplicates_folder` | `test_duplicate_invoice_goes_to_duplicates_folder` |
| Review | incomplete / ambiguous / own-society issuer | missing number, intercompany, unknown supplier |
| Review (fuzzy buyer) | `test_fuzzy_buyer_goes_to_review` | `test_purchase_order_fuzzy_matches_society_by_name` |
| Quarantine | (placement) | empty text, reader error, unstable download, failed archive |

Fuzzy buyer matching (threshold 0.90, margin 0.05) is a review path.
`decide_filing` sends `buyer.fuzzy` to `_PARA_REVISAR` with an auditable
score. The runner-up is left unused. `test_buyer.py` covers the match
itself (near-identical name, alias, trade name, below-threshold, two close
candidates).

The invariant still applies: on uncertainty the file goes to review or
quarantine.

## UI smokes

`tests/ui/test_main_window.py` builds `MainWindow` from `ui.shell`. The
`window` fixture skips (`pytest.skip`) when `ctk.CTk()` cannot open a
display. CI installs `xvfb` and `python3-tk` and wraps pytest with
`xvfb-run -a`. Locally, a machine without a display drops the smokes and
the rest of the suite still runs.

The smokes check that the window builds, switches `monitor` / `history` /
`config`, collects settings, toggles the engine button, applies a
`RESULT` event, imports Excel through `UiMailbox`, and that wired buttons
reach their controllers. `tests/ui/test_outcomes.py` covers
`count_key`, `status_label`, `history_row` and `count_pdfs` without a
display.

## Coverage

`[tool.coverage.run]` measures `automator` and omits `*/ui/*`.
`[tool.coverage.report] fail_under = 90` fails CI and `make check` when
core coverage drops below 90 percent. UI smokes exist to catch composition
breakage; they are outside the floor.

## Import contracts

`[tool.importlinter]` in `pyproject.toml` has three contracts:

- **Clean layers**: `automator.ui` -> `automator.services` -> `automator.domain`
- **Domain does not import config**: `automator.domain` stays free of
  `automator.config`
- **Config does not import services**: `automator.config` stays free of
  `automator.services`

`make import-lint` / `PYTHONPATH=src lint-imports` is the local command.

## File size

`scripts/check_file_size.py` walks `src/automator/**/*.py` and fails any
module over 200 lines. `ALLOWLIST` is empty. An allowlisted path that
drops back under 200, or an entry whose file is gone, also fails so the
list stays empty on purpose.

## Adding a filing rule

Policy first, then placement.

1. Add or extend a case in `tests/domain/test_filing.py` against
   `decide_filing` (and `is_reliable` / `tests/domain/test_buyer.py` when
   the change is about the buyer). Assert the `ProcessOutcome` and the
   `base_folder`.
2. Drive the same case through `InvoiceProcessor` in
   `tests/services/test_processor.py`. Inject the PDF text with the
   `extractor=` lambda and `make_config` / `dummy_pdf`. Assert the file
   landed under review, quarantine, unclassified, duplicates or the
   society folder.
3. If the input text is reusable, put it in `tests/fixtures/invoices.py`.

That order keeps `decide_filing` as the source of truth and uses the
processor test only to prove placement still honours it.

## Fictional data

Names and CUITs in fixtures and tests are invented (`COMPRADORA UNO SA`,
`PROVEEDOR EJEMPLO SRL`, `30111111118`, `30999999995`). Real companies,
real CUITs and production invoices stay out of the tree.
