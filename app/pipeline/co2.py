"""
CO2 estimation engine — GHG Protocol Scopes 1 & 2.

Emission factors (Tunisia, 2023–24):
  Scope 1  — Natural gas combustion : 0.201 kgCO2/kWh_LHV (IPCC AR6)
  Scope 2  — STEG grid electricity  : 0.593 kgCO2/kWh     (ANME Tunisia)
  Scope 2 credit — grid injection   : −0.593 kgCO2/kWh    (avoided grid emission)

Gas LHV: 9.51 kWh/Nm³ (used for combustion CO2, not HHV billing value)

Two modes:
  simple   — direct emission per record, no interaction effects
  trigen   — tri-gen adjusted: credits electricity produced, heat recovered, cooling
"""

import uuid
from typing import Union

from app.models.schemas import (
    CO2Estimate,
    EnergyRecord,
    EnergyType,
    GHGScope,
    StegBillRecord,
    StegMeterReadingRecord,
)
from app.pipeline.normalize import GAS_LHV_FACTOR

# ── Emission factors ──────────────────────────────────────────────────────────

EF_GAS_KG_PER_KWH_LHV  = 0.201   # kgCO2/kWh_LHV — IPCC AR6 natural gas
EF_GAS_KG_PER_NM3      = EF_GAS_KG_PER_KWH_LHV * GAS_LHV_FACTOR   # ≈ 1.912
EF_ELEC_GRID_KG_PER_KWH = 0.593  # kgCO2/kWh — ANME Tunisia grid avg

# Tri-gen adjustment constants
TRIGEN_COOLING_COP = 3.2          # equivalent COP of absorption chiller vs electric

AnyRecord = Union[StegBillRecord, StegMeterReadingRecord, EnergyRecord]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_estimate(
    record_id: str,
    date: str,
    scope: GHGScope,
    energy_type: EnergyType,
    quantity_kwh: float,
    emission_factor: float,
    zone: str = "global",
    note: str | None = None,
) -> CO2Estimate:
    co2_kg = round(quantity_kwh * emission_factor, 4)
    return CO2Estimate(
        record_id=record_id,
        date=date,
        scope=scope,
        energy_type=energy_type,
        quantity_kwh=round(quantity_kwh, 4),
        emission_factor=emission_factor,
        co2_kg=co2_kg,
        zone=zone,
        note=note,
    )


# ── Per-record-type estimators ────────────────────────────────────────────────

def _co2_from_steg_bill(record: StegBillRecord) -> list[CO2Estimate]:
    if not record.active_energy_kwh:
        return []
    return [_make_estimate(
        record_id=record.document_id,
        date=record.date,
        scope=GHGScope.scope_2,
        energy_type=EnergyType.electricity,
        quantity_kwh=record.active_energy_kwh,
        emission_factor=EF_ELEC_GRID_KG_PER_KWH,
        zone="global",
        note="STEG bill active energy → Scope 2",
    )]


def _co2_from_steg_meter(record: StegMeterReadingRecord) -> list[CO2Estimate]:
    estimates = []
    rid = record.document_id

    purchase_slots = [
        record.purchase_jour_kwh,
        record.purchase_pointe_kwh,
        record.purchase_nuit_kwh,
        record.purchase_soir_kwh,
    ]
    purchase_total = sum(v for v in purchase_slots if v is not None)
    if purchase_total > 0:
        estimates.append(_make_estimate(
            record_id=rid,
            date=record.date,
            scope=GHGScope.scope_2,
            energy_type=EnergyType.electricity,
            quantity_kwh=purchase_total,
            emission_factor=EF_ELEC_GRID_KG_PER_KWH,
            note="Grid purchase (sum of time slots) → Scope 2",
        ))

    injection_slots = [
        record.injection_jour_kwh,
        record.injection_pointe_kwh,
        record.injection_nuit_kwh,
        record.injection_soir_kwh,
    ]
    injection_total = sum(v for v in injection_slots if v is not None)
    if injection_total > 0:
        estimates.append(_make_estimate(
            record_id=rid,
            date=record.date,
            scope=GHGScope.scope_2_credit,
            energy_type=EnergyType.electricity,
            quantity_kwh=injection_total,
            emission_factor=-EF_ELEC_GRID_KG_PER_KWH,
            note="Grid injection (tri-gen export) → Scope 2 credit",
        ))

    return estimates


def _co2_from_energy_record(record: EnergyRecord) -> list[CO2Estimate]:
    estimates = []
    zone = record.zone or "global"

    if record.energy_type == EnergyType.natural_gas:
        kwh_lhv = (record.quantity_raw * GAS_LHV_FACTOR
                   if record.unit_raw.lower().replace(" ", "") in ("nm3", "nm³", "m3")
                   else (record.quantity_kwh or record.quantity_raw))
        if kwh_lhv > 0:
            estimates.append(_make_estimate(
                record_id=record.document_id,
                date=record.date,
                scope=GHGScope.scope_1,
                energy_type=EnergyType.natural_gas,
                quantity_kwh=kwh_lhv,
                emission_factor=EF_GAS_KG_PER_KWH_LHV,
                zone=zone,
                note=f"Gas combustion LHV ({GAS_LHV_FACTOR} kWh/Nm³) → Scope 1",
            ))

    elif record.energy_type == EnergyType.electricity:
        kwh = record.quantity_kwh or record.quantity_raw

        if zone == "grid_import":
            estimates.append(_make_estimate(
                record_id=record.document_id,
                date=record.date,
                scope=GHGScope.scope_2,
                energy_type=EnergyType.electricity,
                quantity_kwh=kwh,
                emission_factor=EF_ELEC_GRID_KG_PER_KWH,
                zone=zone,
                note="Grid purchase → Scope 2",
            ))
        elif zone == "grid_export":
            estimates.append(_make_estimate(
                record_id=record.document_id,
                date=record.date,
                scope=GHGScope.scope_2_credit,
                energy_type=EnergyType.electricity,
                quantity_kwh=kwh,
                emission_factor=-EF_ELEC_GRID_KG_PER_KWH,
                zone=zone,
                note="Grid injection → Scope 2 credit (negative)",
            ))
        # self_generation: no direct scope 2 assignment; handled by trigen mode if desired

    return estimates


# ── Tri-gen adjusted calculation ──────────────────────────────────────────────

def trigen_co2_breakdown(
    gas_nm3: float,
    electricity_produced_kwh: float,
    heat_recovered_kwh: float,
    cooling_kwh: float,
    date: str = "unknown",
    zone: str = "global",
) -> dict[str, float]:
    """
    Compute net tri-gen CO2 benefit vs. business-as-usual.
    Returns a dict with breakdown of gross and avoided emissions (all in kgCO2).
    """
    gross = gas_nm3 * EF_GAS_KG_PER_NM3
    avoided_elec    = electricity_produced_kwh * EF_ELEC_GRID_KG_PER_KWH
    avoided_heat    = heat_recovered_kwh * EF_GAS_KG_PER_KWH_LHV
    avoided_cooling = (cooling_kwh / TRIGEN_COOLING_COP) * EF_ELEC_GRID_KG_PER_KWH

    net = gross - avoided_elec - avoided_heat - avoided_cooling
    return {
        "gas_nm3": gas_nm3,
        "gross_co2_kg": round(gross, 2),
        "avoided_electricity_kg": round(avoided_elec, 2),
        "avoided_heat_kg": round(avoided_heat, 2),
        "avoided_cooling_kg": round(avoided_cooling, 2),
        "net_co2_kg": round(net, 2),
        "date": date,
        "zone": zone,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def estimate_co2(record: AnyRecord) -> list[CO2Estimate]:
    """
    Dispatch CO2 estimation based on record type.
    Returns a list (may be empty if insufficient data).
    """
    if isinstance(record, StegBillRecord):
        return _co2_from_steg_bill(record)
    if isinstance(record, StegMeterReadingRecord):
        return _co2_from_steg_meter(record)
    if isinstance(record, EnergyRecord):
        return _co2_from_energy_record(record)
    return []


def estimate_co2_batch(records: list[AnyRecord]) -> list[CO2Estimate]:
    """Estimate CO2 for a list of heterogeneous records."""
    results = []
    for rec in records:
        results.extend(estimate_co2(rec))
    return results
