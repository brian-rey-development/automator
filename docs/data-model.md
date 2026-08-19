# Data model

The domain types are frozen values in `domain/models.py`, `domain/buyer.py`, `domain/suppliers.py` and `config/model.py`. Filing, duplicate detection and the UI all share the same invoice, identity and outcome shapes. Configuration companies and the SQLite supplier registry are two different party models that happen to share a CUIT.

## Voucher and parsed invoice

A `Voucher` is a `VoucherKind` (`FC`, `NC`, `ND`) plus a letter. Its `label` is the pair used on disk, for example `FC A`. `DocumentType` distinguishes a normal invoice from an `orden_compra`; purchase orders use the type label `OC` instead of the voucher label.

`ParsedInvoice` is the parser's complete, immutable reading of one PDF. It carries the voucher, sales point, number, supplier display name, optional `buyer_cuit`, `ambiguous_buyer`, issue date, `document_type`, optional `buyer_name` and optional `issuer_cuit`. `full_number` joins sales point and number as `0001-00000123`. `type_label` is `OC` for a purchase order and `voucher.label` otherwise.

`has_number` is true when the number and sales point are more than the parser fillers `00000000` and `0000`. `has_supplier` is true when `supplier` is more than `UNKNOWN_SUPPLIER` (`PROVEEDOR_DESCONOCIDO`). Those two flags gate identity and reliability.

`identity` is the ledger key used for name-based duplicates: `normalize_name(supplier)|full_number|type_label`. It is present only when both `has_number` and `has_supplier` hold. `issuer_identity` is the exact CUIT key `issuer_cuit|full_number|type_label`, present only when `has_number` and `issuer_cuit` both hold. The parser fills `issuer_cuit` through `unique_issuer_cuit`; a registry hit later overwrites it with the canonical supplier CUIT.

## Process outcomes and results

`ProcessOutcome` is the recorded fate of a file: `moved`, `dry_run`, `unclassified`, `duplicate`, `needs_review`, `quarantined`, `skipped_missing`, `error`. `ProcessResult` pairs the source path with that outcome, an optional destination, the parsed invoice (when one was produced), a Spanish message, and an optional `intended` outcome. Dry-run sets `outcome` to `DRY_RUN` and `intended` to the decision that would have applied. `counted_outcome` prefers `intended` when it is set, so session stats follow the real policy.

Three module-level tuples group outcomes for later layers. `FILED_OUTCOMES` is `MOVED` and `UNCLASSIFIED`: only those rows count as already archived for duplicate checks. `SESSION_ARCHIVED` is `MOVED` and `DRY_RUN`, the monitor's "archived" counter. `UNDOABLE_OUTCOMES` is `MOVED`, `UNCLASSIFIED`, `DUPLICATE`, `NEEDS_REVIEW` and `QUARANTINED`, so review and quarantine can be undone the same way as a filed copy.

## CUIT

`Cuit` is an `Annotated[str, AfterValidator(require_valid_cuit)]`. `require_valid_cuit` runs `coerce_cuit` then AFIP modulo-11 via `is_valid_cuit`. A CUIT is 11 digits. `coerce_cuit` rebuilds a 9 or 10 digit value as type (2) plus a zero-padded DNI body (8) plus check digit, and keeps the rebuild only when `is_valid_cuit` accepts it.

`extract_cuits` finds 11-digit candidates with optional separators, bounded so a CAE or concatenated run is skipped, and keeps those that pass `is_valid_cuit`. `unique_issuer_cuit(text, buyer_cuit)` subtracts the buyer from that set and returns the leftover CUIT only when exactly one remains. Zero or two-plus leftovers yield `None`, so `issuer_identity` stays empty.

## Companies and suppliers

`SocietyMapping` in `config/model.py` is a buying company stored in `config.json`. The JSON field is `name` (kept for 1.0.x files), with optional `trade_name` (also accepted as `nombre_fantasia`) and `aliases`. `match_names()` is `(name, trade_name?, *aliases)`, the strings buyer matching compares. The destination folder is derived as `base/{sanitized name}` rather than stored on the mapping.

`Supplier` in `domain/suppliers.py` is an issuer. Python fields are `cuit`, `legal_name`, `trade_name` and `extra_aliases`. SQLite still stores `razon_social` and `nombre_fantasia` (see `docs/persistence.md`). `aliases()` is the frozen set of `normalize_name` keys built from legal name, trade name and extra aliases.

`merge_supplier(existing, incoming)` keeps the incoming legal name and prefers the incoming trade name. The previous legal name and, when it changed, the previous trade name are appended as extra aliases, so later name matching still finds the old wording.

## Supplier matching

`SupplierRegistry` is an immutable in-memory index. CUIT lookup is exact against valid leftover CUITs. `match(text, exclude_cuits)` computes `extract_cuits(text) - exclude_cuits` (the worker excludes the resolved buyer CUIT so the company's own number is skipped). A unique registered CUIT in that leftover set is the match. Zero hits, or two-plus registered CUITs, return `None`.

Leftover CUITs that fail the unique CUIT hit skip the name fallback: an unknown or colliding CUIT on the page cannot be overwritten by a known alias. Name fallback runs only when the leftover set is empty. It scans normalized invoice text for aliases of length `_MIN_TEXT_ALIAS` (5) or more, still excluding `exclude_cuits`, and accepts a match only when exactly one supplier remains. Zero or two-plus name hits return `None`. Short aliases such as `SA` are ignored so they cannot hit every invoice.

## Buyer matching

`resolve_buyer` in `domain/buyer.py` prefers an exact CUIT. An `ambiguous_buyer` flag from the parser (two of the configured CUITs appear in the text) returns `BuyerResolution` with `ambiguous=True` and no CUIT. A unique `invoice.buyer_cuit` returns that CUIT at score `1.0`. When only `buyer_name` is present, `_fuzzy_match` scores `SequenceMatcher` on `normalize_name` against every `SocietyLike.match_names()`.

The winner must reach `_FUZZY_THRESHOLD` (`0.90`). If the runner-up sits within `_FUZZY_MARGIN` (`0.05`), the result is ambiguous with no CUIT. A unique score at or above the threshold returns the candidate CUIT with `fuzzy=True`. Filing policy still sends that candidate to review: the CUIT is a proposal for the operator, and `decide_filing` files under `folders.review`.

## Name normalization

`normalize_name` in `domain/names.py` is the single comparable key: NFKD, combining marks stripped, whitespace collapsed, case folded. Invoice identity, supplier alias indexes, fuzzy buyer scores and `SupplierRegistry.search` all go through it. `LegalName` rejects a blank razon social at the Pydantic boundary.

## Filenames

`sanitize_component` in `domain/filenames.py` strips Windows-illegal characters (`\\ / * ? : " < > |` and control whitespace), trims dots and spaces, and caps each segment at `_MAX_COMPONENT_LENGTH` (150). An empty result falls back to `UNKNOWN_SUPPLIER`. `build_filename` produces `{supplier} {type_label} {full_number}.pdf` after sanitizing the supplier.

Destination templates in `domain/filing/destination.py` split on `/`, fill `{supplier}`, `{society}`, `{year}`, `{month}` and `{day}` (missing dates become `sin_fecha`), and sanitize each segment the same way.

## Validation errors

`format_validation_error` joins every Pydantic error, stripping the `Value error, ` prefix. `first_validation_error` formats only the first error and prefixes a Spanish field label from `_FIELD_LABELS` (`cuit` to `CUIT`, `name` and `legal_name` to `Razon social`, `trade_name` to `Nombre de fantasia`). Excel import and the society dialogs use the first-error form; settings save uses the full join.
