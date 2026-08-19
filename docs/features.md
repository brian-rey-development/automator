# Features

Everything is configurable from the interface. The app ships empty of companies
and CUITs: on first launch a wizard collects the input folder, the output folder
and, optionally, a first company.

## Invoice classification

- **Voucher detection** by AFIP code (01 = FC A, 06 = FC B, 08 = NC B, and the
  rest of the published set), with a text-based fallback when the code is
  absent. Purchase orders are recognized from a header-anchored
  `ORDEN DE COMPRA` line and file under the orders folder instead of the
  invoice tree.
- **Number and point of sale**, accepting both the split and the combined
  layout.
- **Supplier** identified against the imported supplier registry. A unique CUIT
  or unique alias in the invoice text canonicalizes the legal name, so every
  layout of the same issuer lands in one folder. Zero matches or two or more
  matches leave the PDF label as-is; a missing supplier, or a supplier that
  equals one of your own companies, goes to review.
- **Buyer company** by CUIT against the configured companies. When the CUIT is
  absent, a name match at or above 0.90 (with a 0.05 margin over the runner-up)
  proposes a candidate and filing policy sends it to review.
- **Issue date**, used by the folder template (`sin_fecha` when it is missing).

The parser returns deterministic defaults on unexpected text. It surfaces
uncertainty through the models (`UNKNOWN_SUPPLIER`, filler numbers, an
ambiguous-buyer flag) rather than raising.

## Safe routing

Each invoice ends up in a place that depends on how reliable the reading was.
`decide_filing` is the only policy. A fuzzy buyer match is `NEEDS_REVIEW` and
lands in `_PARA_REVISAR`.

| Situation | Destination | Status |
|---|---|---|
| Buyer company detected by CUIT | Company folder | Filed |
| Buyer CUIT missing, name below 0.90 | `_SIN_CLASIFICAR` | Unclassified |
| Already filed before (duplicate) | `_DUPLICADOS` | Duplicate |
| Incomplete data or doubtful supplier | `_PARA_REVISAR` | Review |
| Several of your own companies appear | `_PARA_REVISAR` | Review |
| Buyer matched only by name (fuzzy) | `_PARA_REVISAR` | Review |
| Unreadable PDF or error | `_ERRORES` | Quarantine |

Purchase orders use the same outcomes. The archive root is the orders folder,
with `_SIN_SOCIEDAD` as the company segment when the buyer is unknown.

The guiding principle is **No invoice is ever misfiled or lost silently.**
When in doubt, the file goes to review.

## Two categories: companies and suppliers

- **Companies** (buyers) are your own entities: CUIT, legal name, optional trade
  name and aliases. Each one files under a standardized folder
  `base/{Razon Social}` (the folder is derived from the legal name). They can be
  added one by one or imported from Excel.
- **Suppliers** (issuers) are imported from Excel into a registry in
  `history.db`: CUIT, legal name, trade name and alias variants. The registry
  canonicalizes each invoice's supplier name. A search box finds any supplier
  among thousands of rows. The worker reads an immutable in-memory snapshot,
  rebuilt after each import.

Both imports read `.xlsx` with tolerant headers (accents, case and dots are
ignored), fold extra alias columns in, dedupe by CUIT and report per-row errors
(bad check digit, empty legal name) while keeping the valid rows. The registry
is optional: if it is empty, filing uses the label read from the PDF.

## Configurable folder structure

The destination for an invoice is `base/{empresa}/{proveedor}`: the buyer
company resolves the top folder, and inside it a template with tokens is
applied:

- `{supplier}` - supplier company name (canonical, the default)
- `{society}` - company folder
- `{year}` `{month}` `{day}` - from the issue date (or `sin_fecha`)

Examples: `{supplier}` (the default) files by supplier;
`{year}/{month}/{supplier}` files by year and month. The final PDF name is
`{supplier} {type} {sales_point}-{number}.pdf`.

## Audit history

Everything processed is stored in SQLite and survives closing the app. The
History view shows each row with its result and destination. On top of this:

- **Undo**: returns the last undoable placement to the input folder. The monitor
  must be stopped first, so the watcher stays idle during the return. If marking
  the ledger fails, the file is moved back to the destination.
- **Retry pending**: reprocesses whatever was left in `_PARA_REVISAR` and
  `_ERRORES`, including PDFs nested under a supplier subfolder. Useful after
  adding a company or fixing the configuration.

## Duplicate detection

An invoice is identified by `normalize_name(supplier)|number|type`. When the
issuer CUIT is present, a second exact key `issuer_cuit|number|type` also
matches, so a supplier rename still finds the earlier filing. Only MOVED and
UNCLASSIFIED outcomes count as already filed, and only while that previous
destination still exists on disk. A new copy of the same voucher then goes to `_DUPLICADOS`, which is the usual
case when AFIP lets the same voucher be downloaded again.

## Copy instead of move

An option to copy each invoice to its destination and leave the original in the
input folder. The app records a stable signature (path, size, modified time) of
every processed source in the audit history, so the watcher and the periodic
rescan skip a file that has already been handled. Retrying from review or
quarantine still moves, so those folders drain. Copy-mode undo forgets the
source signature so the original can be processed again. Move is the default
and drains the input folder.

## Robustness

- Waits for the download to finish before moving (the file size has to stop
  changing within the timeout).
- Placements use `shutil.move` or `shutil.copy2`, work across drives, and append
  ` (2)`, ` (3)`, ... on name collision.
- Quarantines unreadable or empty PDFs while the monitor keeps running. A
  periodic rescan of the input folder (every 60 seconds) catches events the
  watcher missed.
- Validated, immutable configuration, saved atomically, with a fallback if the
  file is corrupted so the app still opens.

## Notices and utilities

- **Persistent pending notice** read from `_PARA_REVISAR` and `_ERRORES` on a
  timer.
- **System notification** (optional) when the pending count increases.
- **Test mode** (dry-run): shows the intended destination and leaves files in
  place. The intended outcome is still recorded for the session counters.
- Buttons to open the input, output, review and log folders.

## History

- **Undo** returns the last filed PDF to the input folder and marks the ledger
  row as reverted. Undoable outcomes are moved, unclassified, duplicate, review
  and quarantine. Copy-mode undo also forgets the source signature.
- **Vaciar historial** clears processing history and remembered source
  signatures only. PDFs stay where they are.
- **Reintentar pendientes** walks `_PARA_REVISAR` and `_ERRORES` recursively.

## First launch

When you open the app for the first time (`config.json` is still missing), a
wizard asks for the bare minimum (input folder, output folder and, optionally, a
first company). Everything can be changed later from Configuration.
