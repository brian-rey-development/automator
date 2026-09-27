"""Sample invoice texts and fictitious CUITs used across the suite."""

import base64
import json

CUIT_ONE = "30111111118"
CUIT_TWO = "30222222229"

FACTURA_A_TEXT = """ORIGINAL
FACTURA
A
Cod. 01
Razon Social: PROVEEDOR EJEMPLO SRL
CUIT: 30-99999999-5
Fecha de Emision: 01/08/2026
Punto de Venta: 0001    Comp. Nro: 00000123
Periodo Facturado
CUIT: 30-11111111-8
Razon Social: COMPRADORA UNO SA
"""

NOTA_CREDITO_B_TEXT = """ORIGINAL
NOTA DE CREDITO
B
Cod. 08
Razon Social: PROVEEDOR DOS SA
Punto de Venta: 0003    Comp. Nro: 00000045
CUIT: 30-22222222-9
"""

NOTA_DEBITO_B_TEXT = """ORIGINAL
NOTA DE DEBITO
B
Cod. 07
Razon Social: PROVEEDOR TRES SA
Punto de Venta: 0005    Comp. Nro: 00000009
CUIT: 30-22222222-9
"""

COMBINED_NUMBER_TEXT = """FACTURA
Cod. 01
Comp. Nro: 0002-00000777
Razon Social: DISTRIBUIDORA NORTE
"""

NO_RAZON_SOCIAL_TEXT = """MI PROVEEDOR SIN ETIQUETA
Cod. 01
Punto de Venta: 0009   Comp. Nro: 00000001
"""

COMPROBANTE_WORD_TEXT = """FACTURA
A
Razon Social: PROVEEDOR LOMBARDI SA
Punto de Venta:
1238
Comprobante Nro:
00002972
CUIT: 30-69746598-3
Ingresos Brutos: 90230-69746598-3
"""

INLINE_NUMERO_TEXT = """PROVEEDOR VERCELLI
IVA Responsable Inscripto
FACTURA Nº 0007 - 00001522
Fecha: 05/08/2026
Razon Social: PROVEEDOR VERCELLI SA
CUIT: 20238054428
"""

STANDALONE_TABLE_TEXT = """FACTURA
A
Razon Social: PROVEEDOR BASILICO
33-55438074-9
0004 - 00004899
06/08/2026
20-17427308-2
"""

AMBIGUOUS_STANDALONE_TEXT = """FACTURA
A
Razon Social: PROVEEDOR DUDOSO
0003-00010452
0007-00099999
"""

ONLY_IIBB_TEXT = """FACTURA
A
Razon Social: PROVEEDOR SIN NUMERO
Ingresos Brutos: 90230-69746598-3
CUIT: 30-69746598-3
"""

SPLIT_NUMBER_TEXT = """FACTURA
A
Cod. 01 00082809
Punto de venta: 0022 Numero:
Razon Social: PROVEEDOR JUNIN SA
"""

COLUMN_BLEED_SUPPLIER_TEXT = """FACTURA
A
Razon Social: PROVEEDOR COLUMNA SRL          Domicilio: CALLE FALSA 123
Punto de Venta: 0001 Comp. Nro: 00000123
"""

COLUMN_BLEED_ORDER_TEXT = """GRUPO X
ORD COMPRA  NRO: 2026-00004050
Unidad Ejecutora: CHACO                 Proveedor: JIMENEZ LORENZO HECTOR
Sociedad: ANDREOLI AGRO S.A.            Domicilio: CHACRA 15 0
Responsable Inscripto CUIT: 30711637253
"""

ORDEN_COMPRA_TEXT = """GRUPO EJEMPLO
RUTA 30 - KM 88.5
ORD COMPRA  NRO: 2026-00004046
Fecha: 15/08/2026
Unidad Ejecutora: AUTOMOTRIZ
Sociedad: COMPRADORA UNO SA
Responsable Inscripto CUIT: 30111111118
Proveedor: FERRETERIA EJEMPLO SRL
Cond. Iva: Responsable No Inscripto CUIT: 30-99999999-4
Total: 774,534.00
"""

ORDEN_COMPRA_NO_CUIT_TEXT = """GRUPO EJEMPLO
ORD COMPRA  NRO: 2026-00004050
Sociedad: COMPRADORA UNO S.A.
Proveedor: FERRETERIA EJEMPLO SRL
Total: 100,000.00
"""

# Shapes below reproduce real issuer layouts that the text parser used to miss.
SUPPLIER_CUIT = "30999999995"

INVOICE_QUOTING_ORDER_TEXT = """                 A              FACTURA
      COD. 001                  Comprobante N°:       00003-00010650
Proveedor Ejemplo SRL           C.U.I.T.:  30-99999999-5
Cliente:   COMPRADORA UNO SA    C.U.I.T.:  30-11111111-8
ORDEN DE COMPRA N-2026-0002726 -- UNIDAD 12
        Comprobante autorizado          C.A.E. N°: 86383515447719
"""

ABBREVIATED_COMPR_LABEL_TEXT = """        A        NOTA DE CREDITO
                 Cod.:03
    PROVEEDOR EJEMPLO SA     Punto de Venta:    0006     Compr.Nro.:    00007910
 Razon Social:     6727-COMPRADORA UNO S.A.
    CUIT:  30-11111111-8
    CAE N°:       86361401733548
"""

SEMICOLON_SCRAMBLED_TEXT = """          FACTURA
     A    PUNTO DE VENTA Nº:     COMP. NRO.;0002     16787
RAZON SOCIAL: PROVEEDOR EJEMPLO SA     Cod. 01
 CUIT:   30-11111111-8     COMPRADORA UNO SA
"""

TITLE_NUMBER_TEXT = """     A        Fecha de Emisión:   09/09/2026
   COD.01
             Factura  0009-8569
   C.U.I.T   30-99999999-5
 Razón Social:   COMPRADORA UNO S.A.     CUIT:  30-11111111-8
     0014-00017930(1259534)/0014-00018033(1262983)/0010-00025443(1268170)
"""

CREDIT_NOTE_QUOTING_INVOICE_TEXT = """NOTA DE CREDITO
Cod. 03
Razon Social: PROVEEDOR EJEMPLO SA
Anula: Factura 0003-00001234
"""

REMITO_NEXT_TO_NUMBER_TEXT = """        00002-00025065
        Fecha 10/09/2026
Sr/es   COMPRADORA UNO SA   C.U.I.T.  30-11111111-8
Condiciones  VALORES A 7 DIAS F.F.   Remito    0001-00069500
        CAE: 86372405673700
"""

# A pre-printed form: the issuer header is an image, only the customer is text.
PREPRINTED_FORM_TEXT = """        00002-00003590
Sr/es   CLIENTE AJENO SA   C.U.I.T.  30-70773021-4
        CAE: 86350805625735
"""


def afip_qr_url(host: str = "www.afip.gob.ar/fe/qr/", **overrides: object) -> str:
    """An AFIP QR URL as printed on electronic vouchers (RG 4892)."""
    payload: dict[str, object] = {
        "ver": 1,
        "fecha": "2026-09-17",
        "cuit": int(SUPPLIER_CUIT),
        "ptoVta": 3,
        "tipoCmp": 1,
        "nroCmp": 10650,
        "importe": 1570580,
        "moneda": "PES",
        "ctz": 1,
        "tipoDocRec": 80,
        "nroDocRec": int(CUIT_ONE),
        "tipoCodAut": "E",
        "codAut": 86383515447719,
    }
    payload.update(overrides)
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return f"https://{host}?p={encoded}"
