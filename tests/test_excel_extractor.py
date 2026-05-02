"""
Tests for the Excel operational-report extractor.
openpyxl is mocked — no real files needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime
from unittest.mock import patch, MagicMock
import pytest

from app.extractors.excel import (
    _parse_cell_date,
    _date_from_filename,
    _delta,
    _to_num,
    _scan_rows,
    extract_excel,
)
from app.models.schemas import DocumentType, EnergyType


# ── _parse_cell_date ──────────────────────────────────────────────────────────

def test_parse_cell_date_from_datetime():
    assert _parse_cell_date(datetime(2025, 8, 31)) == "2025-08"

def test_parse_cell_date_from_ddmmyyyy_string():
    assert _parse_cell_date("31/08/2025") == "2025-08"

def test_parse_cell_date_from_iso_string():
    assert _parse_cell_date("2025-08-31") == "2025-08"

def test_parse_cell_date_returns_none_for_garbage():
    assert _parse_cell_date("N/A") is None
    assert _parse_cell_date(None) is None


# ── _date_from_filename ───────────────────────────────────────────────────────

def test_date_from_filename_french_uppercase():
    assert _date_from_filename("FIN AOUT 2025_2292025.xlsx") == "2025-08"

def test_date_from_filename_french_lowercase():
    assert _date_from_filename("avril-report1_2442026.xlsx") == "2026-04"

def test_date_from_filename_english():
    assert _date_from_filename("july-report1_2442026.xlsx") == "2026-07"

def test_date_from_filename_no_month():
    assert _date_from_filename("unknown_file.xlsx") is None


# ── _to_num ───────────────────────────────────────────────────────────────────

def test_to_num_int():
    assert _to_num(18634) == 18634.0

def test_to_num_float():
    assert _to_num(3.14) == 3.14

def test_to_num_string_with_space():
    assert _to_num("18 634") == 18634.0

def test_to_num_string_comma_decimal():
    assert _to_num("1234,56") == 1234.56

def test_to_num_none():
    assert _to_num(None) is None

def test_to_num_invalid():
    assert _to_num("abc") is None


# ── _delta ────────────────────────────────────────────────────────────────────

def test_delta_normal_cumulative():
    assert _delta([1000.0, 1100.0, 1200.0, 1500.0]) == 500.0

def test_delta_single_value():
    assert _delta([42.0]) == 42.0

def test_delta_empty():
    assert _delta([]) is None


# ── _scan_rows ────────────────────────────────────────────────────────────────

def _make_ws(rows):
    """Build a mock worksheet from a list of row tuples."""
    ws = MagicMock()
    ws.iter_rows = MagicMock(return_value=iter(rows))
    return ws


def test_scan_rows_extracts_gas():
    rows = [
        # (A,       B,                                              C,    D,       E)
        ("Consommation gaz", "Consommation du gaz naturel moteur en Nm3 (Volume)", None, 100.0, 200.0),
        (None,      "Date",                                        None, datetime(2025, 8, 1), datetime(2025, 8, 31)),
    ]
    ws = _make_ws(rows)
    result = _scan_rows(ws)
    assert result["gas_motor_nm3"] == [100.0, 200.0]
    assert len(result["_date_row"]) == 2


def test_scan_rows_extracts_grid_purchase():
    rows = [
        ("Achat et vente", "Energie Positive Steg KWh", None, 1000.0, 1500.0),
    ]
    ws = _make_ws(rows)
    result = _scan_rows(ws)
    assert result["grid_purchase_kwh"] == [1000.0, 1500.0]


def test_scan_rows_skips_zero_and_none():
    rows = [
        ("Consommation gaz", "Consommation du gaz naturel moteur en Nm3 (Volume)", None, None, "abc", 50.0),
    ]
    ws = _make_ws(rows)
    result = _scan_rows(ws)
    assert result["gas_motor_nm3"] == [50.0]   # None and "abc" filtered by _to_num


# ── extract_excel (mocked workbook) ──────────────────────────────────────────

def _make_mock_wb(rows):
    """Full mock of openpyxl.load_workbook returning a sheet with the given rows."""
    ws = MagicMock()
    ws.iter_rows = MagicMock(return_value=iter(rows))

    wb = MagicMock()
    wb.sheetnames = ["BILAN TOTAL"]
    wb.__getitem__ = lambda self, key: ws
    wb.close = MagicMock()
    return wb


def test_extract_excel_returns_records_for_known_rows():
    rows = [
        (None,              "Date",                                             None, datetime(2025, 8, 31)),
        ("Consommation gaz","Consommation du gaz naturel moteur en Nm3 (Volume)",None, 2800000.0, 2864976.0),
        ("Achat et vente",  "Energie Positive Steg KWh",                        None, 1034861.0, 1034861.0),  # zero delta → skipped
        ("Achat et vente",  "Energie Negative Steg KWh",                        None, 4901469.0, 4908517.0),
        ("Achat et vente",  "Energie Positive Production KWh",                  None, 11807237.0, 11834367.0),
    ]
    with patch("app.extractors.excel.openpyxl.load_workbook", return_value=_make_mock_wb(rows)):
        records = extract_excel("FIN AOUT 2025_2292025.xlsx")

    assert len(records) == 3  # grid purchase skipped (zero delta)

    gas_rec = next(r for r in records if r.energy_type == EnergyType.natural_gas)
    assert gas_rec.quantity_raw == pytest.approx(64976.0)
    assert gas_rec.unit_raw == "Nm3"
    assert gas_rec.date == "2025-08"
    assert gas_rec.quantity_kwh is None      # left for normalize.py

    injection_rec = next(r for r in records if r.energy_type == EnergyType.electricity and "injection" in r.document_id.lower() or r.quantity_raw == pytest.approx(7048.0))
    assert injection_rec.quantity_raw == pytest.approx(7048.0)


def test_extract_excel_date_fallback_to_filename():
    """When no date header, use filename."""
    rows = [
        ("Consommation gaz","Consommation du gaz naturel moteur en Nm3 (Volume)", None, 100.0, 200.0),
    ]
    with patch("app.extractors.excel.openpyxl.load_workbook", return_value=_make_mock_wb(rows)):
        records = extract_excel("FIN AOUT 2025_2292025.xlsx")

    assert all(r.date == "2025-08" for r in records)


def test_extract_excel_all_zero_deltas_returns_empty():
    rows = [
        ("Achat et vente", "Energie Positive Steg KWh", None, 1000.0, 1000.0),
    ]
    with patch("app.extractors.excel.openpyxl.load_workbook", return_value=_make_mock_wb(rows)):
        records = extract_excel("dummy.xlsx")

    assert records == []


def test_extract_excel_zone_mapping():
    rows = [
        (None, "Date", None, datetime(2025, 12, 31)),
        ("Energymeter eau chaude Gamma", "Energie en kWh ", None, 700000.0, 718000.0),
    ]
    with patch("app.extractors.excel.openpyxl.load_workbook", return_value=_make_mock_wb(rows)):
        records = extract_excel("Fin-Decembre_2322026.xlsx")

    assert any(r.zone == "gamma" for r in records)


def test_extract_excel_document_type():
    rows = [
        (None, "Date", None, datetime(2025, 7, 31)),
        ("Energie Moteur", "Energie éléctrique au borne de l'alternateur en KWh", None, 9000000.0, 9027000.0),
    ]
    with patch("app.extractors.excel.openpyxl.load_workbook", return_value=_make_mock_wb(rows)):
        records = extract_excel("FIN JUILLET 2025.xlsx")

    assert all(r.document_type == DocumentType.excel_report for r in records)
    assert all(r.extraction_method == "openpyxl_delta" for r in records)
