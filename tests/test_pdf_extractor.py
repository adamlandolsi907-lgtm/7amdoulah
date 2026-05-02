"""
Tests for the PDF extractor.
Ollama API calls and pymupdf rendering are mocked — no model server needed.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import patch, MagicMock
import pytest
from PIL import Image as PILImage

from app.extractors.pdf import (
    _has_text_layer,
    _extract_text_page,
    _extract_page_vision,
    extract_pdf,
)
from app.models.schemas import DocumentType, EnergyType

_DUMMY_IMAGE = PILImage.new("RGB", (200, 300))


# ── _has_text_layer ───────────────────────────────────────────────────────────

def test_has_text_layer_returns_true_for_rich_text():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "FACTURE STEG " * 5  # >50 chars
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    with patch("pdfplumber.open", return_value=mock_pdf):
        assert _has_text_layer("fake.pdf") is True


def test_has_text_layer_returns_false_for_no_text():
    mock_page = MagicMock()
    mock_page.extract_text.return_value = None
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page]
    mock_pdf.__enter__ = lambda s: mock_pdf
    mock_pdf.__exit__ = MagicMock(return_value=False)
    with patch("pdfplumber.open", return_value=mock_pdf):
        assert _has_text_layer("fake.pdf") is False


def test_has_text_layer_returns_false_on_exception():
    with patch("pdfplumber.open", side_effect=Exception("corrupt")):
        assert _has_text_layer("fake.pdf") is False


# ── _extract_text_page ────────────────────────────────────────────────────────

def test_text_page_extracts_kwh_and_date():
    text = "Facture STEG - 03/2025\nConsommation 18 634 kWh\nMontant total"
    rec = _extract_text_page(text, "invoice.pdf")
    assert rec is not None
    assert rec.quantity_kwh == 18634.0
    assert rec.date == "2025-03"
    assert rec.unit_raw == "kWh"
    assert rec.extraction_method == "pdfplumber_text"


def test_text_page_returns_none_for_non_energy():
    text = "Random document with no energy content at all."
    rec = _extract_text_page(text, "other.pdf")
    assert rec is None


def test_text_page_handles_missing_date():
    text = "Fiche relevé énergie\nConsommation 5000 kWh"
    rec = _extract_text_page(text, "releve.pdf")
    assert rec is not None
    assert rec.date == "unknown"
    assert rec.quantity_kwh == 5000.0


# ── _extract_page_vision ──────────────────────────────────────────────────────

def test_vision_page_steg_bill():
    with patch("app.extractors.pdf.classify_image", return_value=DocumentType.steg_bill), \
         patch("app.extractors.pdf._extract_bill") as mock_bill:
        mock_bill.return_value = MagicMock(extraction_confidence=0.95)
        result = _extract_page_vision(_DUMMY_IMAGE, "doc.pdf", page_num=1)
    mock_bill.assert_called_once_with(_DUMMY_IMAGE, "doc.pdf:p1")


def test_vision_page_meter_reading():
    with patch("app.extractors.pdf.classify_image", return_value=DocumentType.steg_meter_reading), \
         patch("app.extractors.pdf._extract_meter_reading") as mock_meter:
        mock_meter.return_value = MagicMock(extraction_confidence=0.90)
        result = _extract_page_vision(_DUMMY_IMAGE, "releve.pdf", page_num=2)
    mock_meter.assert_called_once_with(_DUMMY_IMAGE, "releve.pdf:p2")


def test_vision_page_unknown_falls_back_to_energy_record():
    vision_response = json.dumps({
        "date": "2025-06",
        "active_energy_kwh": 12000,
        "confidence": 0.45,
    })
    with patch("app.extractors.pdf.classify_image", return_value=DocumentType.unknown), \
         patch("app.extractors.pdf._call_ollama", return_value=vision_response):
        rec = _extract_page_vision(_DUMMY_IMAGE, "misc.pdf", page_num=1)
    assert rec.date == "2025-06"
    assert rec.quantity_kwh == 12000.0
    assert rec.extraction_confidence <= 0.5
    assert rec.extraction_method == "ollama_vision_fallback"


def test_vision_page_unknown_ollama_error_returns_empty_record():
    with patch("app.extractors.pdf.classify_image", return_value=DocumentType.unknown), \
         patch("app.extractors.pdf._call_ollama", side_effect=Exception("timeout")):
        rec = _extract_page_vision(_DUMMY_IMAGE, "broken.pdf", page_num=1)
    assert rec.date == "unknown"
    assert rec.extraction_confidence == 0.0


# ── extract_pdf ───────────────────────────────────────────────────────────────

def test_extract_pdf_uses_vision_for_scanned():
    """Scanned PDF: _has_text_layer=False → render pages → vision extraction."""
    fake_bill = MagicMock()
    fake_bill.date = "2025-09"
    fake_bill.extraction_confidence = 0.92

    with patch("app.extractors.pdf._has_text_layer", return_value=False), \
         patch("app.extractors.pdf._render_pages", return_value=[_DUMMY_IMAGE, _DUMMY_IMAGE]), \
         patch("app.extractors.pdf._extract_page_vision", return_value=fake_bill) as mock_vision:
        records = extract_pdf("scan.pdf")

    assert len(records) == 2
    assert mock_vision.call_count == 2


def test_extract_pdf_uses_text_for_native_pdf():
    """Native PDF: _has_text_layer=True → pdfplumber text path."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Facture STEG 04/2025\nConsommation 9 000 kWh"
    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.pages = [mock_page]
    mock_pdf_ctx.__enter__ = lambda s: mock_pdf_ctx
    mock_pdf_ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.extractors.pdf._has_text_layer", return_value=True), \
         patch("pdfplumber.open", return_value=mock_pdf_ctx):
        records = extract_pdf("native.pdf")

    assert len(records) == 1
    assert records[0].quantity_kwh == 9000.0


def test_extract_pdf_text_falls_through_to_vision_when_no_records():
    """Text layer exists but yields no parseable records → fall through to vision."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Some text but not energy data " * 5
    mock_pdf_ctx = MagicMock()
    mock_pdf_ctx.pages = [mock_page]
    mock_pdf_ctx.__enter__ = lambda s: mock_pdf_ctx
    mock_pdf_ctx.__exit__ = MagicMock(return_value=False)

    fake_rec = MagicMock()
    fake_rec.date = "unknown"
    fake_rec.extraction_confidence = 0.3

    with patch("app.extractors.pdf._has_text_layer", return_value=True), \
         patch("pdfplumber.open", return_value=mock_pdf_ctx), \
         patch("app.extractors.pdf._render_pages", return_value=[_DUMMY_IMAGE]), \
         patch("app.extractors.pdf._extract_page_vision", return_value=fake_rec):
        records = extract_pdf("fallthrough.pdf")

    assert len(records) == 1
    assert records[0].date == "unknown"
