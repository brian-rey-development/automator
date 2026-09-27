# 11. AFIP QR as the authoritative voucher source

- Status: accepted
- Date: 2026-09-27
- Deciders: Brian Rey

## Context

A batch of 12 real invoices from the client all landed in `_PARA_REVISAR`. Each failure was a regex miss on one issuer's layout: `Compr.Nro.`, `COMP. NRO.;0002  16787`, an unpadded `Factura 0009-8569`, a `Remito` number next to the voucher number, and invoices quoting the buyer's purchase order on a line of its own. Three were pre-printed forms whose issuer header is a scanned image: the text layer only holds the customer, so no regex can ever find the issuer.

Every electronic voucher since RG 4892/2020 carries a QR: a URL on `afip.gob.ar` / `arca.gob.ar` whose `p` parameter is base64 JSON with `cuit` (issuer), `ptoVta`, `nroCmp`, `tipoCmp`, `tipoDocRec`/`nroDocRec` (receiver) and `codAut` (CAE). 11 of the 12 PDFs embed it as an image, including the three pre-printed forms. It is machine-generated and identical in shape across issuers.

## Decision

`services/pdf_reader.read_qr_payloads` decodes QRs from the images embedded in the first pages (pypdf + Pillow + zxing-cpp). It never raises: no QR is normal and yields `()`.

`domain/parser/afip_qr.parse_afip_qr` accepts only AFIP/ARCA hosts, keys in any casing, standard or URL-safe base64 with or without padding, and validates the issuer CUIT check digit and number ranges. Anything else is `None`. `unique_afip_qr` keeps a QR only when all decoded payloads describe the same voucher.

With a QR, `parse_invoice` always parses a factura and `merge_qr` overlays it: voucher kind and letter, point of sale and number, issuer CUIT, issue date, and the buyer (the receiver CUIT when it is one of our companies, otherwise none). The printed width (`00003` vs `0003`) is kept when it agrees with the QR, so names and duplicate keys match what the text-only parser produced. The result has `qr_verified=True`, and `_canonicalize_supplier` then looks the issuer up by CUIT (`SupplierRegistry.by_cuit`) instead of scanning the text, so no other CUIT on the page can win.

The QR carries no name. A verified issuer missing from the registry keeps the printed `Razon Social` or, failing that, goes to review.

## Consequences

The text parser becomes the fallback for documents without a QR (older vouchers, non-fiscal copies). It also got the fixes from the same batch, since those documents still exist: a CAE means an invoice and never an order, `Compr.` and `;` labels, the title number for invoices only, and `Remito` / associated / quoted invoice numbers excluded from the standalone fallback.

A scan with no text layer but a readable QR is no longer quarantined; it is parsed from the QR and reviewed if the supplier is unknown.

`pillow` and `zxing-cpp` become runtime dependencies and are listed in `automator.spec`. Decoding costs up to about 300 ms on a full-page scanned form.

## Alternatives considered

### OCR of the header

Tesseract adds a large native bundle to the `.exe`, and OCR of a CUIT can misread digits. The QR is exact and already present.

### Render pages to find vector-drawn QRs

pypdfium2 could rasterize pages when no QR image exists. None of the sampled PDFs needed it, so it stays out until a real document does.

### Query AFIP's voucher verification service

It needs the issuer CUIT as input, network access and credentials. The QR already carries what it would return.
