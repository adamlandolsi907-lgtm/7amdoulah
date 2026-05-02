"""
Tests for the image extractor.
Claude API calls are mocked — no API key needed to run these.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from unittest.mock import patch, MagicMock
import pytest

from app.extractors.image import (
    _parse_json,
    _to_float as _float,
    classify_image,
    _extract_bill,
    _extract_meter_reading,
)
from app.models.schemas import DocumentType
from PIL import Image as PILImage

# Dummy PIL image used in all mocked calls
_DUMMY_IMAGE = PILImage.new("RGB", (100, 100))


# ── _parse_json ───────────────────────────────────────────────────────────────

def test_parse_json_clean():
    raw = '{"type": "steg_bill"}'
    assert _parse_json(raw) == {"type": "steg_bill"}

def test_parse_json_strips_markdown_fence():
    raw = '```json\n{"type": "steg_bill"}\n```'
    assert _parse_json(raw) == {"type": "steg_bill"}

def test_parse_json_strips_fence_no_lang():
    raw = '```\n{"a": 1}\n```'
    assert _parse_json(raw) == {"a": 1}


# ── _float ────────────────────────────────────────────────────────────────────

def test_float_none():
    assert _float(None) is None

def test_float_int():
    assert _float(18634) == 18634.0

def test_float_string_with_space():
    assert _float("18 634") == 18634.0

def test_float_string_with_comma_decimal():
    assert _float("18634,5") == 18634.5

def test_float_invalid():
    assert _float("N/A") is None


# ── classify_image (mocked) ───────────────────────────────────────────────────

def _mock_claude_response(text: str):
    """Build a fake Anthropic response object."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def test_classify_steg_bill():
    with patch("app.extractors.image._call_ollama", return_value='{"type": "steg_bill"}'):
        result = classify_image(_DUMMY_IMAGE)
    assert result == DocumentType.steg_bill


def test_classify_meter_reading():
    with patch("app.extractors.image._call_ollama", return_value='{"type": "steg_meter_reading"}'):
        result = classify_image(_DUMMY_IMAGE)
    assert result == DocumentType.steg_meter_reading


def test_classify_unknown_on_error():
    with patch("app.extractors.image._call_ollama", side_effect=Exception("network error")):
        result = classify_image(_DUMMY_IMAGE)
    assert result == DocumentType.unknown


# ── _extract_bill (mocked) ────────────────────────────────────────────────────

_MOCK_BILL_RESPONSE = json.dumps({
    "date": "2025-10",
    "facture_number": "69105258R",
    "active_energy_kwh": 18634,
    "reactive_energy_kvarh": 3859,
    "power_subscribed_kva": 1300,
    "amount_tnd": 14372.921,
    "site": "STE ADWYA",
    "district": "KRAM",
    "confidence": 0.97,
})

def test_extract_bill_fields():
    with patch("app.extractors.image._call_ollama", return_value=_MOCK_BILL_RESPONSE):
        record = _extract_bill(_DUMMY_IMAGE, "WhatsApp Image (38).jpeg")

    assert record.date == "2025-10"
    assert record.facture_number == "69105258R"
    assert record.active_energy_kwh == 18634.0
    assert record.reactive_energy_kvarh == 3859.0
    assert record.power_subscribed_kva == 1300.0
    assert record.amount_tnd == 14372.921
    assert record.site == "STE ADWYA"
    assert record.district == "KRAM"
    assert record.extraction_confidence == 0.97
    assert record.extraction_method == "ollama_vision"
    assert record.source_file == "WhatsApp Image (38).jpeg"
    assert record.supplier == "STEG"


def test_extract_bill_handles_nulls():
    sparse = json.dumps({
        "date": "2025-11",
        "facture_number": None,
        "active_energy_kwh": None,
        "confidence": 0.4,
    })
    with patch("app.extractors.image._call_ollama", return_value=sparse):
        record = _extract_bill(_DUMMY_IMAGE, "test.jpeg")

    assert record.date == "2025-11"
    assert record.active_energy_kwh is None
    assert record.facture_number is None


# ── _extract_meter_reading (mocked) ──────────────────────────────────────────

_MOCK_METER_RESPONSE = json.dumps({
    "date": "2025-02",
    "client_ref": "226570",
    "purchase_jour_kwh": 7175.0,
    "purchase_pointe_kwh": 3648.0,
    "purchase_nuit_kwh": 5075.0,
    "purchase_soir_kwh": 1992.0,
    "purchase_reactive_kvarh": 6348.0,
    "injection_jour_kwh": 75.0,
    "injection_pointe_kwh": 0.0,
    "injection_nuit_kwh": 0.0,
    "injection_soir_kwh": 0.0,
    "net_consumption_kwh": None,   # let extractor compute it
    "max_demand_j_kva": 1.6,
    "max_demand_p_kva": 1.6,
    "max_demand_s_kva": 1.6,
    "confidence": 0.93,
})

def test_extract_meter_fields():
    with patch("app.extractors.image._call_ollama", return_value=_MOCK_METER_RESPONSE):
        record = _extract_meter_reading(_DUMMY_IMAGE, "releve_feb25.jpeg")

    assert record.date == "2025-02"
    assert record.client_ref == "226570"
    assert record.purchase_jour_kwh == 7175.0
    assert record.injection_jour_kwh == 75.0
    assert record.extraction_confidence == 0.93


def test_meter_net_consumption_computed():
    """net_consumption_kwh should be computed when Claude returns null."""
    with patch("app.extractors.image._call_ollama", return_value=_MOCK_METER_RESPONSE):
        record = _extract_meter_reading(_DUMMY_IMAGE, "releve_feb25.jpeg")

    # purchase total = 7175 + 3648 + 5075 + 1992 = 17890
    # injection total = 75 + 0 + 0 + 0 = 75
    # net = 17890 - 75 = 17815
    assert record.net_consumption_kwh == pytest.approx(17815.0)


def test_meter_net_provided_by_claude():
    """If Claude provides net_consumption_kwh, use it directly."""
    data = json.loads(_MOCK_METER_RESPONSE)
    data["net_consumption_kwh"] = 17800.0
    with patch("app.extractors.image._call_ollama", return_value=json.dumps(data)):
        record = _extract_meter_reading(_DUMMY_IMAGE, "releve_feb25.jpeg")
    assert record.net_consumption_kwh == 17800.0
