# 4. Dual duplicate identity

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

AFIP lets a user download the same voucher again. The filer has to recognize that second PDF as already archived, or the supplier folder fills with copies. A supplier's printed name also changes (trade name vs legal name, a later Excel import that canonicalizes `legal_name`). A key built only from the printed name would treat the renamed issuer as a new invoice. A key built only from CUIT would miss documents that have a number and a name but no extractable issuer CUIT.

The ledger is the memory of what was already filed. The identity scheme has to survive a rename and stay exact enough that two different vouchers stay distinct.

## Decision

`ParsedInvoice` exposes two keys in `src/automator/domain/models.py`.

`identity` is `normalize_name(supplier)|full_number|type_label`. It is present only when `has_number` and `has_supplier` are true. Example: `acme s.a.|0001-00000123|FC A`. Purchase orders use `type_label` `OC`.

`issuer_identity` is `issuer_cuit|full_number|type_label`. It is present only when `has_number` and `issuer_cuit` are set. Example: `30712345673|0001-00000123|FC A`.

`Ledger.record` writes both, plus `issuer_cuit`, into `records`. Schema v3 added `issuer_identity` (see ADR 0009).

`Ledger.archived_destination(identity, issuer_cuit)` looks up with equality only (`identity = ?`, and when a CUIT is passed, `issuer_identity = ?` built as `{issuer_cuit}|{number}|{type}` via `_identity_suffix`). There is no `LIKE`. The `outcome` filter is `FILED_OUTCOMES`, which is `(ProcessOutcome.MOVED, ProcessOutcome.UNCLASSIFIED)`. Review, duplicate, quarantine, dry-run, and error rows are ignored. Reverted rows (`reverted = 1`) are ignored. The latest matching destination wins.

`is_archived_duplicate` in `engine/worker.py` then checks that this destination still exists on disk (`path_exists`). A ledger row whose file was deleted is a ghost, and the next copy is filed again.

## Consequences

A second download of a filed invoice goes to `_DUPLICADOS` with `ProcessOutcome.DUPLICATE`. A later Excel import that changes the printed supplier name still hits the same `issuer_identity`, so `tests/services/test_ledger.py` (`test_archived_destination_matches_renamed_supplier_via_issuer_cuit`) stays green.

Review and quarantine stays out of the duplicate set. Sending a half-parsed PDF to `_PARA_REVISAR` must leave the next complete copy free to file.

The worker pays a filesystem `exists` check on every candidate duplicate. That is the price of refusing phantom duplicates after the user empties a company folder.

Both keys can be missing (no number, unknown supplier, no issuer CUIT). Those invoices have no identity, so they cannot be duplicates. They already go to review by reliability.

## Alternatives considered

### Name identity only

`normalize_name(supplier)|number|type` is cheap and works without a CUIT. A canonical rename after import would file the same voucher again under the new folder. The CUIT key exists so the issuer, not the spelling, is the party.

### Issuer CUIT identity only

That key is the stable one when the CUIT is on the page. Many scans and some purchase orders have a number and a name only. Those would slip through as new files. Both keys stay, and either hit is enough.

### LIKE or substring match on identity

A prefix match would catch slight name drift. It would also collide `acme` with `acme norte` and merge distinct vouchers. Equality on the two full keys keeps collisions out of the archive.
