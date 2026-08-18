# Configuration

All configuration is edited from the interface (Configuration tab) and saved in
`config.json`. There is no need to touch the file by hand.

## File locations

Paths follow the conventions of each operating system (via `platformdirs`):

- **Configuration**: `config.json` in the user's config directory.
- **History**: `history.db` in the user's data directory.
- **Logs**: `automator.log` in the user's log directory.

From the app: Configuration -> "Open logs folder".

## Fields

### Main folders

- **Input folder**: where downloaded PDFs land (this is the folder being
  watched).
- **Output folder**: root where the sorted invoices are stored.

### Companies

List of buyer companies. Each one has:

- **CUIT**: 11 digits (hyphens and dots are accepted, normalized automatically).
- **Company name** (Razon Social): visible name, cannot be empty.
- **Trade name** (Nombre de Fantasia) and **aliases**: optional, used to match
  the buyer by name when the CUIT is not present.

The destination folder is not chosen by hand: it is `base/{Razon Social}`. They
are added, edited and removed from the interface, or imported from Excel. The app
starts with no company: you define your own.

### Suppliers

Registry of invoice issuers, imported from Excel and stored in `history.db`
(SQLite). Each supplier has a CUIT, legal name, optional trade name and alias
variants. When a known supplier is found in an invoice (by CUIT or name), its
legal name canonicalizes the filing so every variant lands in one folder. The
registry is searched from the interface and can be cleared. It is optional: with
no registry, filing falls back to the label read from the PDF.

### Options

- **Test mode**: moves nothing, only shows what it would do.
- **Copy instead of move**: leaves the original in the input folder and places a
  copy in the destination. The app remembers each already-processed file (by
  path, size and date, in the history) so it does not re-copy it on every
  rescan. Disabled by default: it moves (the input folder empties itself).
- **Wait for the download to finish**: avoids moving half-downloaded files.
- **Maximum wait (seconds)**: 0 to 120.
- **Notifications**: system notice when pending items increase.
- **Folder structure**: template inside each company's folder.

### Automatic folders (advanced)

- **Unclassified**: invoices from a CUIT that is not configured.
- **Quarantine**: unreadable PDFs or PDFs with errors.

In addition, two folders are created on their own inside the output folder:
`_PARA_REVISAR` (manual review) and `_DUPLICADOS`.

## Folder template

Defines subfolders inside each company's folder. Valid tokens:

| Token | Value |
|---|---|
| `{supplier}` | Supplier company name |
| `{society}` | Name of the company folder |
| `{year}` | Year of the issue date (or `sin_fecha`) |
| `{month}` | Month (or `sin_fecha`) |
| `{day}` | Day (or `sin_fecha`) |

Examples:

- `{supplier}` (the default) -> `.../Company/SUPPLIER/invoice.pdf`
- `{year}/{month}/{supplier}` -> `.../Company/2026/08/SUPPLIER/invoice.pdf`

An invalid token is rejected on save.

## Validation rules

- The output folders cannot be inside the input folder (this avoids a
  reprocessing loop).
- CUITs cannot be repeated across companies, and every CUIT (companies and
  suppliers) must pass the AFIP check digit.

If something does not validate, the interface reports it and does not save until
it is fixed.
