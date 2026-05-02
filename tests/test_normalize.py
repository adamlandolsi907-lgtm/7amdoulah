import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.pipeline.normalize import normalize, gas_kwh_lhv, NON_CONVERTIBLE


# ── Identity ──────────────────────────────────────────────────────────────────

def test_kwh_identity():
    kwh, factor, _ = normalize(1000.0, "kWh")
    assert kwh == 1000.0
    assert factor == 1.0

def test_kwh_case_insensitive():
    kwh, _, _ = normalize(500.0, "KWH")
    assert kwh == 500.0


# ── SI electrical ─────────────────────────────────────────────────────────────

def test_mwh():
    kwh, factor, _ = normalize(1.0, "MWh")
    assert kwh == 1000.0
    assert factor == 1000.0

def test_gwh():
    kwh, _, _ = normalize(1.0, "GWh")
    assert kwh == 1_000_000.0


# ── SI thermal ────────────────────────────────────────────────────────────────

def test_gj():
    kwh, factor, _ = normalize(1.0, "GJ")
    assert abs(kwh - 277.778) < 0.001
    assert factor == 277.778

def test_mj():
    kwh, _, _ = normalize(3600.0, "MJ")
    assert abs(kwh - 1000.0) < 0.1


# ── Caloric ───────────────────────────────────────────────────────────────────

def test_gcal():
    kwh, factor, _ = normalize(1.0, "Gcal")
    assert kwh == 1163.0
    assert factor == 1163.0

def test_thermie():
    kwh, factor, _ = normalize(1.0, "th")
    assert kwh == 1.163
    assert factor == 1.163


# ── Imperial ──────────────────────────────────────────────────────────────────

def test_btu():
    kwh, factor, _ = normalize(1.0, "BTU")
    assert abs(kwh - 0.000293071) < 1e-6  # limited by round(..., 6)

def test_toe():
    kwh, factor, _ = normalize(1.0, "toe")
    assert kwh == 11630.0

def test_mmbtu():
    kwh, _, _ = normalize(1.0, "MMBtu")
    assert abs(kwh - 293.071) < 0.001


# ── Gas volumetric ────────────────────────────────────────────────────────────

def test_nm3_gas():
    kwh, factor, formula = normalize(100.0, "Nm3")
    assert kwh == 1055.0
    assert factor == 10.55
    assert "PCS" in formula or "Tunisia" in formula

def test_nm3_unicode():
    kwh, _, _ = normalize(100.0, "Nm³")
    assert kwh == 1055.0


# ── Steam ─────────────────────────────────────────────────────────────────────

def test_steam_tonnes():
    kwh, factor, _ = normalize(1.0, "t")
    assert kwh == 681.0
    assert factor == 681.0

def test_steam_t_vapeur():
    kwh, _, _ = normalize(2.0, "T vapeur")
    assert kwh == 1362.0


# ── Non-convertible ───────────────────────────────────────────────────────────

def test_kvarh_not_converted():
    kwh, factor, formula = normalize(500.0, "kVArh")
    assert kwh is None
    assert factor == 0.0
    assert "non-convertible" in formula

def test_kvar_not_converted():
    kwh, _, _ = normalize(100.0, "kvar")
    assert kwh is None


# ── Error handling ────────────────────────────────────────────────────────────

def test_unknown_unit_raises():
    with pytest.raises(ValueError, match="Unknown unit"):
        normalize(1.0, "furlongs_per_fortnight")


# ── Gas LHV ──────────────────────────────────────────────────────────────────

def test_gas_lhv():
    result = gas_kwh_lhv(100.0)
    assert result == 951.0  # 100 Nm³ × 9.51 kWh/Nm³


# ── Real values from STEG bills ───────────────────────────────────────────────

def test_steg_bill_october_2025():
    """From WhatsApp Image (38): active energy 18,634 kWh."""
    kwh, factor, _ = normalize(18634.0, "kWh")
    assert kwh == 18634.0
    assert factor == 1.0

def test_cross_unit_consistency():
    """1 toe should equal 10 Gcal within rounding."""
    toe_kwh, _, _ = normalize(1.0, "toe")
    gcal_kwh, _, _ = normalize(10.0, "Gcal")
    assert abs(toe_kwh - gcal_kwh) < 1.0  # within 1 kWh tolerance
