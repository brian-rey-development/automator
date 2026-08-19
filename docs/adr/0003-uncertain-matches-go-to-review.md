# 3. Uncertain matches go to review

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

The product promise is simple. No invoice is misfiled or lost in silence. AFIP PDFs are messy. Two of the user's companies can appear on one voucher. A purchase order may print a buyer name with no CUIT. A supplier line can look like a configured society. An unreadable scan has no text at all.

Earlier drafts treated a fuzzy buyer name (threshold 0.90) as good enough to file as `MOVED`. A 93% name match can still be the wrong company, and the archive would look certain. The live rule, also recorded in `docs/architecture.md` and `docs/how-it-works.md`, is that a name-only match is a proposal for a human.

## Decision

On any uncertainty the file goes to review or quarantine. Automatic `MOVED` requires an exact buyer CUIT, a reliable parse, and a new identity.

Review (`ProcessOutcome.NEEDS_REVIEW`, folder `_PARA_REVISAR`) covers these cases, in the order `decide_filing` applies them.

Ambiguous buyer. `parse_invoice` sets `ambiguous_buyer` when two or more configured CUITs appear in the text (`detect_buyer_cuit`). `resolve_buyer` also sets `ambiguous` when two fuzzy name scores sit within `_FUZZY_MARGIN` (0.05). Either path yields review.

Incomplete parse. `is_reliable` is false when the invoice has no number (`0000-00000000`), no supplier (`PROVEEDOR_DESCONOCIDO`), or the supplier name matches a configured society (legal name, trade name, or alias, after `normalize_name`). Those invoices go to review because the issuer is unknown or looks like the buyer.

Leftover CUITs after subtracting the buyer. `SupplierRegistry.match` computes `extract_cuits(text) - exclude_cuits`. A unique leftover CUIT in the registry canonicalizes `supplier` and `issuer_cuit`. Zero or two-plus hits mean no match. If leftover CUITs remain after that, the name fallback is skipped (`return None`). An unknown CUIT on the page is a signal to stop guessing the issuer, even when a long alias also appears in the text. Name fallback itself requires a unique alias of at least `_MIN_TEXT_ALIAS` (5) characters.

Fuzzy buyer always review. Exact CUIT wins (`score` 1.0, `fuzzy` false) and may file. `SequenceMatcher` on normalized names, with `_FUZZY_THRESHOLD` 0.90 and margin 0.05, may propose a `BuyerResolution.cuit`, and `decide_filing` still sends it to review with the percent in the message. Fuzzy matching proposes a buyer; the destination is `_PARA_REVISAR`.

Quarantine (`ProcessOutcome.QUARANTINED`, folder `_ERRORES`) is for files the parser cannot even see. Empty or whitespace-only PDF text, an extractor exception, a download that never stabilizes, and a failed place all go there. If quarantine itself fails, the outcome is `ERROR` and the file stays in the input folder for retry.

Unclassified (`UNCLASSIFIED`, `_SIN_CLASIFICAR` or orders `_SIN_SOCIEDAD`) is the remaining honest path. The parse is reliable, the buyer is neither ambiguous nor fuzzy, and no configured CUIT matched. The file is archived, and the outcome tells the user the buyer is unknown.

## Consequences

`tests/domain/test_filing.py` and `tests/services/test_processor.py` treat fuzzy purchase orders (`ORDEN_COMPRA_NO_CUIT_TEXT`) as `NEEDS_REVIEW`, intercompany invoices as review, unknown suppliers as review, and empty PDFs as quarantine.

The user has to visit `_PARA_REVISAR`. That is the cost of the invariant. Retry (`Inbox.reprocess_pending`) walks review and quarantine recursively so a later CUIT or registry import can file the same PDF for real.

CUIT matching stays the only automatic file path because a check-digit-valid CUIT in the configured set is an identity, and a name is an opinion.

## Alternatives considered

### Fuzzy buyer files as MOVED

Filing at 0.90 with an auditable message would empty the review folder faster. It would also put a near-miss company into `base/{Razon Social}` with status "Archivado". The invariant forbids a silent-looking success on a guess. Review keeps the percent in the message so the user can confirm.

### Closest CUIT or first configured company as fallback

Picking a buyer when none is on the page would always produce a destination. It would also mix companies. Unclassified exists so the file is kept, under a folder that says the buyer was missing.

### Leave uncertain files in the input folder

The watcher would pick them up forever. Review and quarantine are real destinations with outcomes, so the ledger can show what happened and retry can find them later.
