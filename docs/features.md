# Features

Everything is configurable from the interface. The app ships with no company or
CUIT preloaded: on first launch a wizard helps you define the bare minimum.

## Invoice classification

- **Voucher detection** by AFIP code (01 = FC A, 06 = FC B, 08 = NC B, etc.),
  with a text-based fallback when the code is not present.
- **Number and point of sale**, tolerating both the split and the combined
  layout.
- **Supplier** identified against the imported supplier registry: any known
  supplier's CUIT (or name) found in the invoice text canonicalizes the filing
  name, so the same supplier always lands in the same folder no matter how its
  invoice is laid out. Falls back to the "Razon Social" label when the supplier
  is not registered; if nothing is detected with confidence the invoice goes to
  review (never filed under an invented name).
- **Buyer company** by CUIT, against the configured companies.
- **Issue date**, used by the folder template.

## Safe routing

Each invoice ends up in a place that depends on how reliable the reading was:

| Situation | Destination | Status |
|---|---|---|
| Buyer company detected | Company folder | Filed |
| Buyer CUIT not detected | `_SIN_CLASIFICAR` | Unclassified |
| Already filed before (duplicate) | `_DUPLICADOS` | Duplicate |
| Incomplete data or doubtful supplier | `_PARA_REVISAR` | Review |
| Several of your own companies appear | `_PARA_REVISAR` | Review |
| Unreadable PDF or error | `_ERRORES` | Quarantine |

The guiding principle is **never file incorrectly in silence**: when in doubt,
send it to review.

## Two categories: companies and suppliers

- **Companies** (buyers) are your own entities: CUIT, legal name, optional trade
  name and aliases. Each one files under a standardized folder
  `base/{Razon Social}` (no folder is picked by hand). They can be added one by
  one or imported from Excel.
- **Suppliers** (issuers) are imported from Excel into a registry (SQLite): CUIT,
  legal name, trade name and alias variants. The registry is what canonicalizes
  each invoice's supplier name. A search box finds any supplier without listing
  thousands of rows.

Both imports read `.xlsx` with tolerant headers (accents, case and dots are
ignored), fold extra alias columns in, dedupe by CUIT and report per-row errors
(bad check digit, empty legal name) without aborting the rest.

## Configurable folder structure

The destination is `base/{empresa}/{proveedor}`: the buyer company resolves the
top folder, and inside it a template with tokens is applied:

- `{supplier}` - supplier company name (canonical, the default)
- `{society}` - company folder
- `{year}` `{month}` `{day}` - from the issue date (or `sin_fecha`)

Examples: `{supplier}` (the default) files by supplier;
`{year}/{month}/{supplier}` files by year and month.

## Audit history

Everything processed is stored in SQLite and survives closing the app. The
"History" view shows it with its result and destination. On top of this:

- **Undo**: returns the last move to the input folder (with the monitor
  stopped, so it is not reprocessed immediately).
- **Retry pending**: reprocesses whatever was left in review and quarantine,
  useful after adding a company or fixing the configuration.

## Duplicate detection

An invoice is identified by `supplier | number | type`. If it was already filed
before (according to the history), the new copy goes to `_DUPLICADOS` instead of
being duplicated. Useful when AFIP allows re-downloading the same voucher.

## Copy instead of move

An option to copy each invoice to its destination and leave the original in the
input folder, instead of moving it. The app records a stable signature (path,
size, modified time) of every processed source in the audit history (SQLite), so
the watcher and the periodic rescan never re-copy a file that has already been
handled. Move is the default and drains the input folder as before.

## Robustness

- Waits for the download to finish before moving (avoids half-downloaded files).
- Atomic moves with no overwriting (appends ` (2)`, ` (3)`, ...).
- Quarantines unreadable files without stopping the monitor; periodic rescan of
  the folder in case the watcher misses an event.
- Validated, immutable configuration, saved atomically, with a fallback if the
  file is corrupted (never leaves the app unable to open).

## Notices and utilities

- **Persistent pending notice** read from the folders (it does not depend on a
  single interface event).
- **System notification** (optional) when new pending items appear.
- **Test mode** (dry-run): shows what it would do without moving anything.
- Buttons to open the input, output, review and log folders.

## First launch

When you open the app for the first time, a wizard asks for the bare minimum
(input folder, output folder and, optionally, a first company). Everything can
be changed later from Configuration.
