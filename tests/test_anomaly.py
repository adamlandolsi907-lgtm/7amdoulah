"""
Tests for the anomaly detection engine.
No external dependencies — pure Python.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.pipeline.anomaly import (
    detect_dropout,
    detect_spikes,
    detect_drift,
    detect_reconciliation,
    detect_all,
)
from app.models.schemas import (
    AnomalyType,
    DocumentType,
    EnergyRecord,
    EnergyType,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _elec_record(date: str, kwh: float | None, zone: str = "grid_import") -> EnergyRecord:
    return EnergyRecord(
        document_id=f"test_{date}_{zone}",
        document_type=DocumentType.excel_report,
        source_file=f"report_{date}.xlsx",
        date=date,
        energy_type=EnergyType.electricity,
        quantity_raw=kwh or 0.0,
        unit_raw="kWh",
        quantity_kwh=kwh,
        zone=zone,
    )


def _bill_record(date: str, kwh: float) -> EnergyRecord:
    return EnergyRecord(
        document_id=f"bill_{date}",
        document_type=DocumentType.steg_bill,
        source_file=f"bill_{date}.jpeg",
        date=date,
        energy_type=EnergyType.electricity,
        quantity_raw=kwh,
        unit_raw="kWh",
        quantity_kwh=kwh,
        zone="global",
    )


# ── Detector 1: Dropout ───────────────────────────────────────────────────────

def test_dropout_none_value():
    recs = [_elec_record("2025-08", None)]
    result = detect_dropout(recs)
    assert len(result) == 1
    assert result[0].type == AnomalyType.dropout
    assert result[0].confidence_score == 1.0


def test_dropout_zero_value():
    recs = [_elec_record("2025-08", 0.0)]
    result = detect_dropout(recs)
    assert len(result) == 1
    assert result[0].type == AnomalyType.dropout


def test_dropout_no_flag_normal():
    recs = [_elec_record("2025-08", 18000.0)]
    result = detect_dropout(recs)
    assert result == []


def test_dropout_mixed():
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", None),
        _elec_record("2025-10", 19000.0),
        _elec_record("2025-11", 0.0),
    ]
    result = detect_dropout(recs)
    assert len(result) == 2
    dates = [a.date for a in result]
    assert "2025-09" in dates
    assert "2025-11" in dates


# ── Detector 2: Spike ─────────────────────────────────────────────────────────

def test_spike_detected():
    # Stable series then a 10x spike
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", 18500.0),
        _elec_record("2025-10", 17800.0),
        _elec_record("2025-11", 18200.0),
        _elec_record("2025-12", 180000.0),  # <-- spike
    ]
    result = detect_spikes(recs, z_threshold=3.0)
    assert len(result) >= 1
    assert result[0].type == AnomalyType.spike
    assert result[0].date == "2025-12"


def test_spike_not_detected_normal():
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", 18500.0),
        _elec_record("2025-10", 17800.0),
        _elec_record("2025-11", 18200.0),
        _elec_record("2025-12", 19000.0),  # slight increase, not spike
    ]
    result = detect_spikes(recs, z_threshold=3.0)
    assert result == []


def test_spike_requires_4_points():
    # Only 3 points — not enough for windowed Z-score
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", 18500.0),
        _elec_record("2025-10", 180000.0),
    ]
    result = detect_spikes(recs, z_threshold=3.0)
    assert result == []


def test_spike_confidence_bounded():
    recs = [
        _elec_record("2025-08", 1000.0),
        _elec_record("2025-09", 1000.0),
        _elec_record("2025-10", 1000.0),
        _elec_record("2025-11", 1000.0),
        _elec_record("2025-12", 1_000_000.0),
    ]
    result = detect_spikes(recs, z_threshold=3.0)
    for a in result:
        assert 0.0 <= a.confidence_score <= 1.0


# ── Detector 3: Drift ─────────────────────────────────────────────────────────

def test_drift_upward_detected():
    # 50% monthly increase — far above 10% threshold
    recs = [
        _elec_record("2025-08", 10000.0),
        _elec_record("2025-09", 15000.0),
        _elec_record("2025-10", 22500.0),
        _elec_record("2025-11", 33750.0),
    ]
    result = detect_drift(recs, pct_threshold=0.10)
    assert len(result) >= 1
    assert result[0].type == AnomalyType.drift
    assert result[0].delta_pct > 10


def test_drift_downward_detected():
    recs = [
        _elec_record("2025-08", 30000.0),
        _elec_record("2025-09", 20000.0),
        _elec_record("2025-10", 13000.0),
        _elec_record("2025-11", 8500.0),
    ]
    result = detect_drift(recs, pct_threshold=0.10)
    assert len(result) >= 1
    assert "downward" in result[0].description


def test_drift_stable_no_flag():
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", 18100.0),
        _elec_record("2025-10", 17900.0),
        _elec_record("2025-11", 18050.0),
        _elec_record("2025-12", 18200.0),
        _elec_record("2026-01", 17800.0),
    ]
    result = detect_drift(recs, pct_threshold=0.10)
    assert result == []


def test_drift_requires_4_points():
    recs = [
        _elec_record("2025-08", 10000.0),
        _elec_record("2025-09", 15000.0),
        _elec_record("2025-10", 22500.0),
    ]
    result = detect_drift(recs, pct_threshold=0.10)
    assert result == []


# ── Detector 4: Reconciliation ────────────────────────────────────────────────

def test_reconciliation_discrepancy_flagged():
    excel_recs = [_elec_record("2025-10", 25000.0)]
    bill_recs  = [_bill_record("2025-10", 18634.0)]
    result = detect_reconciliation(excel_recs, bill_recs, tolerance_pct=0.02)
    assert len(result) == 1
    assert result[0].type == AnomalyType.reconciliation
    assert result[0].delta_pct > 2
    assert result[0].value_observed == pytest.approx(25000.0)
    assert result[0].value_expected == pytest.approx(18634.0)


def test_reconciliation_within_tolerance():
    excel_recs = [_elec_record("2025-10", 18640.0)]
    bill_recs  = [_bill_record("2025-10", 18634.0)]
    result = detect_reconciliation(excel_recs, bill_recs, tolerance_pct=0.02)
    assert result == []


def test_reconciliation_different_months_no_flag():
    excel_recs = [_elec_record("2025-09", 25000.0)]
    bill_recs  = [_bill_record("2025-10", 18634.0)]
    result = detect_reconciliation(excel_recs, bill_recs)
    assert result == []


def test_reconciliation_requires_grid_import_zone():
    # Excel record is NOT zone=grid_import → should not be compared
    excel_recs = [_elec_record("2025-10", 25000.0, zone="global")]
    bill_recs  = [_bill_record("2025-10", 18634.0)]
    result = detect_reconciliation(excel_recs, bill_recs, tolerance_pct=0.02)
    assert result == []


# ── detect_all integration ────────────────────────────────────────────────────

def test_detect_all_returns_list():
    recs = [
        _elec_record("2025-08", 18000.0),
        _elec_record("2025-09", None),
    ]
    result = detect_all(recs)
    assert isinstance(result, list)
    # At minimum the dropout should be flagged
    types = [a.type for a in result]
    assert AnomalyType.dropout in types


def test_detect_all_with_bill_reconciliation():
    excel_recs = [_elec_record("2025-10", 25000.0)]
    bill_recs  = [_bill_record("2025-10", 18634.0)]
    all_recs = excel_recs + bill_recs
    result = detect_all(all_recs, bill_records=bill_recs)
    rc = [a for a in result if a.type == AnomalyType.reconciliation]
    assert len(rc) >= 1


def test_anomaly_ids_unique():
    recs = [_elec_record(f"2025-{i:02d}", None) for i in range(1, 6)]
    result = detect_dropout(recs)
    ids = [a.anomaly_id for a in result]
    assert len(ids) == len(set(ids))
