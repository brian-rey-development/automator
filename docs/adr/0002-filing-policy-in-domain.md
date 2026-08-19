# 2. Filing policy in domain

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

Processing a PDF is a mix of IO (read text, wait for a download to settle, place the file) and a product decision (review, duplicate, unclassified, or move). If those live in the same function, every change to "when do we trust a buyer" needs a dummy PDF and a temp tree. The invariant is a policy, and policy has to stay cheap to prove.

The processor already had to know folders, templates, and outcomes. The question was where the order of checks belongs.

## Decision

`decide_filing` in `src/automator/domain/filing/decision.py` is the policy. It takes a `ParsedInvoice`, a `BuyerResolution`, the configured societies, a duplicate flag, and a `FilingFolders` value (`review`, `duplicates`, `archive`). It returns a `FilingDecision` (`outcome`, `base_folder`, `message`).

The order is fixed. Ambiguous buyer goes to `ProcessOutcome.NEEDS_REVIEW` on the review folder. An unreliable parse (`is_reliable` in `reliability.py`) goes to review next. A duplicate goes to the duplicates folder. A fuzzy buyer goes to review even when `BuyerResolution.cuit` is set. Only then does `_archive_choice` pick `UNCLASSIFIED` (no buyer CUIT) or `MOVED`.

`InvoiceProcessor` in `src/automator/services/processing/processor.py` orchestrates IO only. It extracts text, calls `parse_invoice` and `resolve_buyer`, canonicalizes the supplier through `SupplierRegistry.match`, builds `FilingFolders` (review, duplicates, and `archive_base` for invoices vs purchase orders), calls `decide_filing`, and places the file. `destination_dir` in `destination.py` fills the user template (`{supplier}`, `{society}`, `{year}`, `{month}`, `{day}`). Unknown template tokens become empty strings via `_TemplateContext.__missing__`. Segments are sanitized with `sanitize_component`.

`archive_base` sends `DocumentType.ORDEN_COMPRA` under `config.orders_base_for(buyer.cuit)` and invoices under `config.folder_for_cuit(buyer.cuit)`.

## Consequences

`tests/domain/test_filing.py` covers the policy with in-memory `BuyerResolution` values. Fuzzy-buyer review, own-society-as-issuer, and missing supplier are assertions on `FilingDecision`, not on the filesystem.

The processor still chooses the archive root and the duplicate predicate. Those are inputs to the policy, so a test can inject `is_duplicate=lambda _: True` and assert the duplicates folder. Dry-run records `ProcessOutcome.DRY_RUN` with `intended=decision.outcome`, so the UI can show "Simulado · Revisar" while the policy stays untouched.

Messages stay in Spanish because they are user-facing (`_AMBIGUOUS`, `_INCOMPLETE`, `_FUZZY` with `round(buyer.score * 100)`). Identifiers stay in English.

A future outcome still has to land in this one function. Splitting "review reasons" into several processors would fork the invariant.

## Alternatives considered

### Policy inside InvoiceProcessor

`InvoiceProcessor._decide` already builds `FilingFolders` from `AppConfig`. Folding the `if buyer.ambiguous` chain into that method would couple every policy branch to config paths and to PDF extraction. Fuzzy-buyer review would only be provable through `tests/services/test_processor.py`. The domain function exists so the order of checks is a unit.

### One strategy class per outcome

Strategy objects would name each branch. The real policy is a single ordered gate (ambiguity, reliability, duplicate, fuzzy, then archive). Five small functions behind a registry would hide that order, which is the thing reviewers need to see.
