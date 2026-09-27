# 7. Parser deterministic defaults

- Status: accepted
- Date: 2026-08-19
- Deciders: Brian Rey

## Context

AFIP PDFs come from hundreds of issuers. Layouts split the point of sale from the number, print "Comp. Nro" or "Comprobante Nro", bury a CUIT inside a CAE, or mention "orden de compra" in the observations of a real factura. The parser is the first gate of the invariant. If it raises, the worker dies and the file sits in Downloads with no outcome. If it invents a supplier from the first line, the invoice is filed under fiction.

The parser has to return something the rest of the domain can judge (`has_number`, `has_supplier`, `ambiguous_buyer`) on every input, including empty strings and binary garbage that slipped past the reader.

## Decision

`parse_invoice` in `src/automator/domain/parser/__init__.py` is total. Unexpected text yields deterministic defaults and a `ParsedInvoice`, always.

Defaults are `Voucher(INVOICE, "A")` so `type_label` is `FC A`, sales point `0000` and number `00000000` (`default_number` in `numbers.py`), supplier `PROVEEDOR_DESCONOCIDO`, `buyer_cuit` `None`, `issue_date` `None`. `has_number` and `has_supplier` are then false, and `is_reliable` sends the file to review.

Factura vs purchase order is header-anchored. `looks_like_order` matches `(?m)^\s*\bORD(?:EN)?\.?\s+(?:DE\s+)?COMPRA\b`. A factura whose observations mention "ORDEN DE COMPRA" stays `DocumentType.FACTURA` (`test_factura_that_mentions_orden_de_compra_stays_a_factura`). A document with a 14-digit CAE is never an order, even when it quotes the buyer's order on a line of its own (`has_cae`). When the AFIP QR is readable it overrides the text parse entirely (ADR 0011). Orders go through `parse_order` (`type_label` `OC`, supplier from `Proveedor:`, buyer name from `Sociedad:`).

Voucher kind and letter prefer AFIP codes in `afip_codes.py` (`Cod. 01` -> `FC A`, `06` -> `FC B`, `03` -> `NC A`, and the rest of `AFIP_CODES`). Codes are digit-bounded so a CAE after "Codigo" is ignored. Missing codes fall back to the text patterns `NOTA DE CREDITO`, `NOTA DE DEBITO`, `FACTURA`, and a letter `[ABCEM]`. The last fallback is `FC A`.

`extract_cuits` in `domain/cuit.py` keeps valid CUITs only (11 digits, AFIP modulo-11 check, digit boundaries, optional separators). `detect_buyer_cuit` intersects those with `known_cuits`. `unique_issuer_cuit` subtracts the buyer and keeps the leftover only when it is unique. Both `parse_factura` and `parse_order` set `issuer_cuit` that way.

Numbers try anchored labels first, then split "Punto de venta" + "Cod. NN <8 digits>", then a unique standalone `NNNN-NNNNNNNN`. Two standalone candidates collapse to the default rather than picking one.

## Consequences

`tests/domain/test_parser.py` can feed `"\x00\x01 ???"` and empty text and assert `FC A` / `0000-00000000` / `PROVEEDOR_DESCONOCIDO`. The processor then quarantines empty PDF text (no extractable glyphs) and reviews a defaulted parse (text existed, data did not).

Callers skip `try/except` around `parse_invoice`. Failures at this layer are data, not control flow.

The header anchor means a real purchase order has to put "ORDEN DE COMPRA" (or `ORD COMPRA`) at the start of a line. A wrapping layout that only says it mid-sentence is parsed as a factura. That is the safer miss, because a factura filed as an order is a misfile.

Issuer CUIT on the parse feeds `issuer_identity` (ADR 0004) even before the registry canonicalizes the name.

## Alternatives considered

### Raise on unexpected text

A `ParseError` would make the worker's `safe_process` emit `ERROR` and leave the file in the input folder, or force every caller to invent a fallback. Defaults plus `has_number` / `has_supplier` give filing policy a single language for "we could not read this."

### Guess the supplier from the first non-empty line

Many templates put the issuer at the top. Many others put a logo tag, a "ORIGINAL" watermark, or the buyer. `Razon Social:` (facturas) and `Proveedor:` (orders), cut at a two-space column gap (`first_column`), are the only automatic names. Anything else is `PROVEEDOR_DESCONOCIDO` and review.

### Substring "orden de compra" as the order detector

That would catch wrapped headers. It would also reclassify facturas that reference an order number in the body. Line-anchored detection keeps those as facturas.
