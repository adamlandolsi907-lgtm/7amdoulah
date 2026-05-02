"""
Tests for the CO2 estimation engine.
No external dependencies — pure Python math.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.pipeline.co2 import (
    EF_ELEC_GRID_KG_PER_KWH,
    EF_GAS_KG_PER_KWH_LHV,
    EF_GAS_KG_PER_NM3,
    estimate_co2,
    estimate_co2_batch,
    trigen_co2_breakdown,
)
from app.models.schemas import (
    CO2Estimate,
    DocumentType,
    EnergyRecord,
    EnergyType,
    GHGScope,
    StegBillRecord,
    StegMeterReadingRecord,
)

import uuid

def _bill(kwh: float | None, date: str = "2025-08") -> StegBillRecord:
    return StegBillRecord(
        document_id="bill_test01",
        source_file="test.jpeg",
        date=date,
        active_energy_kwh=kwh,
        extraction_method="ollama_vision",
    )


def _meter(purchase: float, injection: float, date: str = "2025-02") -> StegMeterReadingRecord:
    return StegMeterReadingRecord(
        document_id="meter_test01",
        source_file="test.jpeg",
        date=date,
        purchase_jour_kwh=purchase,
        purchase_pointe_kwh=0.0,
        purchase_nuit_kwh=0.0,
        purchase_soir_kwh=0.0,
        injection_jour_kwh=injection,
        injection_pointe_kwh=0.0,
        injection_nuit_kwh=0.0,
        injection_soir_kwh=0.0,
        extraction_method="ollama_vision",
    )


def _energy_rec(energy_type: EnergyType, quantity_raw: float, unit_raw: str,
                zone: str = "global", quantity_kwh: float | None = None) -> EnergyRecord:
    return EnergyRecord(
        document_id=f"rec_{uuid.uuid4().hex[:6]}",
        document_type=DocumentType.excel_report,
        source_file="report.xlsx",
        date="2025-08",
        energy_type=energy_type,
        quantity_raw=quantity_raw,
        unit_raw=unit_raw,
        quantity_kwh=quantity_kwh,
        zone=zone,
    )


# ── Emission factor constants ─────────────────────────────────────────────────

def test_ef_values():
    assert EF_ELEC_GRID_KG_PER_KWH == pytest.approx(0.593)
    assert EF_GAS_KG_PER_KWH_LHV == pytest.approx(0.201)
    assert EF_GAS_KG_PER_NM3 == pytest.approx(0.201 * 9.51, rel=1e-4)


# ── StegBillRecord ────────────────────────────────────────────────────────────

def test_steg_bill_scope2():
    estimates = estimate_co2(_bill(18634.0))
    assert len(estimates) == 1
    e = estimates[0]
    assert e.scope == GHGScope.scope_2
    assert e.energy_type == EnergyType.electricity
    assert e.quantity_kwh == pytest.approx(18634.0)
    assert e.co2_kg == pytest.approx(18634.0 * 0.593, rel=1e-4)


def test_steg_bill_none_kwh_returns_empty():
    assert estimate_co2(_bill(None)) == []


def test_steg_bill_date_propagated():
    estimates = estimate_co2(_bill(1000.0, date="2026-04"))
    assert estimates[0].date == "2026-04"


# ── StegMeterReadingRecord ────────────────────────────────────────────────────

def test_meter_purchase_only():
    estimates = estimate_co2(_meter(17890.0, 0.0))
    assert len(estimates) == 1
    assert estimates[0].scope == GHGScope.scope_2
    assert estimates[0].co2_kg == pytest.approx(17890.0 * 0.593, rel=1e-4)


def test_meter_injection_only():
    estimates = estimate_co2(_meter(0.0, 75.0))
    assert len(estimates) == 1
    assert estimates[0].scope == GHGScope.scope_2_credit
    assert estimates[0].co2_kg == pytest.approx(-75.0 * 0.593, rel=1e-4)


def test_meter_purchase_and_injection():
    estimates = estimate_co2(_meter(17890.0, 75.0))
    assert len(estimates) == 2
    scopes = {e.scope for e in estimates}
    assert GHGScope.scope_2 in scopes
    assert GHGScope.scope_2_credit in scopes


def test_meter_no_data_returns_empty():
    rec = StegMeterReadingRecord(
        document_id="meter_empty",
        source_file="x.jpeg",
        date="2025-01",
        extraction_method="ollama_vision",
    )
    assert estimate_co2(rec) == []


# ── EnergyRecord: natural gas ─────────────────────────────────────────────────

def test_gas_nm3_scope1():
    rec = _energy_rec(EnergyType.natural_gas, 64976.0, "Nm3")
    estimates = estimate_co2(rec)
    assert len(estimates) == 1
    e = estimates[0]
    assert e.scope == GHGScope.scope_1
    expected_kwh_lhv = 64976.0 * 9.51
    assert e.quantity_kwh == pytest.approx(expected_kwh_lhv, rel=1e-4)
    assert e.co2_kg == pytest.approx(expected_kwh_lhv * 0.201, rel=1e-4)


def test_gas_kwh_lhv_direct():
    """If gas is already in kWh, use it directly."""
    rec = _energy_rec(EnergyType.natural_gas, 500000.0, "kWh", quantity_kwh=500000.0)
    estimates = estimate_co2(rec)
    assert len(estimates) == 1
    # unit is kWh, not Nm3 → use quantity_kwh
    assert estimates[0].co2_kg == pytest.approx(500000.0 * 0.201, rel=1e-4)


# ── EnergyRecord: electricity ─────────────────────────────────────────────────

def test_electricity_grid_import_scope2():
    rec = _energy_rec(EnergyType.electricity, 7048.0, "kWh", zone="grid_import", quantity_kwh=7048.0)
    estimates = estimate_co2(rec)
    assert len(estimates) == 1
    assert estimates[0].scope == GHGScope.scope_2
    assert estimates[0].co2_kg == pytest.approx(7048.0 * 0.593, rel=1e-4)


def test_electricity_grid_export_scope2_credit():
    rec = _energy_rec(EnergyType.electricity, 27130.0, "kWh", zone="grid_export", quantity_kwh=27130.0)
    estimates = estimate_co2(rec)
    assert len(estimates) == 1
    e = estimates[0]
    assert e.scope == GHGScope.scope_2_credit
    assert e.co2_kg < 0
    assert e.co2_kg == pytest.approx(-27130.0 * 0.593, rel=1e-4)


def test_electricity_self_generation_no_scope2():
    """On-site generation: no Scope 2 estimate (Scope 1 handled via gas record)."""
    rec = _energy_rec(EnergyType.electricity, 27130.0, "kWh", zone="self_generation")
    assert estimate_co2(rec) == []


# ── Tri-gen adjusted ──────────────────────────────────────────────────────────

def test_trigen_breakdown_structure():
    result = trigen_co2_breakdown(
        gas_nm3=64976.0,
        electricity_produced_kwh=27130.0,
        heat_recovered_kwh=8000.0,
        cooling_kwh=5000.0,
        date="2025-08",
    )
    assert "gross_co2_kg" in result
    assert "net_co2_kg" in result
    assert "avoided_electricity_kg" in result
    assert "avoided_heat_kg" in result
    assert "avoided_cooling_kg" in result


def test_trigen_gross_equals_gas_combustion():
    gas = 64976.0
    result = trigen_co2_breakdown(gas, 0, 0, 0)
    assert result["gross_co2_kg"] == pytest.approx(gas * EF_GAS_KG_PER_NM3, rel=1e-4)


def test_trigen_net_less_than_gross_with_avoided():
    result = trigen_co2_breakdown(64976.0, 27130.0, 8000.0, 5000.0)
    assert result["net_co2_kg"] < result["gross_co2_kg"]


def test_trigen_can_be_co2_negative():
    """Large tri-gen output with efficient heat/cooling can make net negative."""
    result = trigen_co2_breakdown(
        gas_nm3=1000.0,
        electricity_produced_kwh=50000.0,
        heat_recovered_kwh=30000.0,
        cooling_kwh=20000.0,
    )
    assert result["net_co2_kg"] < 0


# ── Batch ─────────────────────────────────────────────────────────────────────

def test_batch_mixed_records():
    records = [
        _bill(18634.0),
        _meter(17890.0, 75.0),
        _energy_rec(EnergyType.natural_gas, 64976.0, "Nm3"),
    ]
    estimates = estimate_co2_batch(records)
    assert len(estimates) == 4   # 1 bill + 2 meter (purchase+injection) + 1 gas

    scopes = {e.scope for e in estimates}
    assert GHGScope.scope_1 in scopes
    assert GHGScope.scope_2 in scopes
    assert GHGScope.scope_2_credit in scopes
