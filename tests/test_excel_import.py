"""Tests for the tolerant Excel importer of suppliers and societies."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from automator.services.excel_import import (
    MissingColumnError,
    map_columns,
    parse_societies,
    parse_suppliers,
    read_rows,
)


def test_map_columns_matches_accented_and_dotted_headers() -> None:
    columns = map_columns(["Razón Social", "Nombre de Fantasía", "C.U.I.T."])
    assert columns["razon_social"] == "Razón Social"
    assert columns["nombre_fantasia"] == "Nombre de Fantasía"
    assert columns["cuit"] == "C.U.I.T."


def test_parse_suppliers_builds_a_valid_supplier() -> None:
    rows = [{"CUIT": "30-99999999-5", "Razón Social": "Distribuidora Nordica SA", "Nombre de Fantasía": "NordSur"}]
    report = parse_suppliers(rows)
    assert report.invalid == []
    assert report.created[0].cuit == "30999999995"
    assert report.created[0].nombre_fantasia == "NordSur"


def test_parse_suppliers_reports_invalid_cuit_without_aborting() -> None:
    rows = [{"CUIT": "123", "Razón Social": "X"}, {"CUIT": "30-99999999-5", "Razón Social": "Buena SA"}]
    report = parse_suppliers(rows)
    assert [s.cuit for s in report.created] == ["30999999995"]
    assert report.invalid[0][0] == 2  # first data row is spreadsheet row 2
    assert "CUIT" in report.invalid[0][1]


def test_parse_suppliers_recovers_cuit_missing_leading_zeros() -> None:
    # Excel/registry dropped the DNI padding: the row must import, not be rejected.
    report = parse_suppliers([{"CUIT": "2012345675", "Razón Social": "Con DNI corto SA"}])
    assert report.invalid == []
    assert report.created[0].cuit == "20012345675"


def test_parse_suppliers_reports_empty_razon_social() -> None:
    report = parse_suppliers([{"CUIT": "30-99999999-5", "Razón Social": "   "}])
    assert report.created == []
    assert "social" in report.invalid[0][1].casefold()


def test_parse_suppliers_missing_cuit_column_raises() -> None:
    with pytest.raises(MissingColumnError):
        parse_suppliers([{"Razón Social": "X"}])


def test_parse_suppliers_merges_duplicate_cuit_aliases() -> None:
    rows = [
        {"CUIT": "30-99999999-5", "Razón Social": "Nordica SA", "Alias": "La Nordica"},
        {"CUIT": "30999999995", "Razón Social": "Nordica SA", "Alias": "Nordica Distrib"},
    ]
    report = parse_suppliers(rows)
    assert len(report.created) == 1
    assert set(report.created[0].extra_aliases) == {"La Nordica", "Nordica Distrib"}


def test_parse_societies_builds_a_mapping() -> None:
    rows = [{"CUIT": "30-11111111-8", "Razón Social": "Compradora Uno SA", "Nombre de Fantasía": "Uno"}]
    society = parse_societies(rows).created[0]
    assert society.cuit == "30111111118"
    assert society.name == "Compradora Uno SA"
    assert society.nombre_fantasia == "Uno"


def test_read_rows_reads_headers_and_numeric_cuit(tmp_path: Path) -> None:
    path = tmp_path / "proveedores.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["CUIT", "Razón Social"])
    sheet.append([30999999995, "Nordica SA"])
    workbook.save(path)

    rows = read_rows(path)
    assert rows == [{"CUIT": "30999999995", "Razón Social": "Nordica SA"}]
