"""
ISO 50001 Energy Performance Indicators (KPIs) for ADWYA factory.

KPIs computed:
  EnPI            — actual / baseline (ratio; >1 means worse than baseline)
  EnB             — rolling average kWh/month (energy baseline)
  grid_dependency — steg_net / total_consumed (%)
  self_sufficiency— trigeneration_kwh / total_consumed (%)
  power_factor    — kWh / sqrt(kWh²+kVArh²)  (target >0.9)
  co2_intensity   — kgCO2 / kWh_total
  total_co2_kg    — absolute CO2 for period
"""

import math
from typing import Optional

from app.models.schemas import CO2Estimate, EnergyRecord, EnergyType


def compute_kpis(
    records: list[EnergyRecord],
    co2_estimates: list[CO2Estimate],
    baseline_kwh_per_month: Optional[float] = None,
) -> dict:
    """
    Compute ISO 50001 KPIs from energy records and CO2 estimates.

    baseline_kwh_per_month: optional external reference baseline.
    If None, EnPI is computed as actual/EnB (self-referential rolling avg).
    """
    grid_import_kwh = [
        r.quantity_kwh for r in records
        if r.energy_type == EnergyType.electricity
        and r.quantity_kwh is not None
        and r.zone == "grid_import"
    ]
    selfgen_kwh = [
        r.quantity_kwh for r in records
        if r.energy_type == EnergyType.electricity
        and r.quantity_kwh is not None
        and r.zone == "self_generation"
    ]
    gas_kwh = [
        r.quantity_kwh for r in records
        if r.energy_type == EnergyType.natural_gas
        and r.quantity_kwh is not None
    ]
    reactive_kvarh = [
        r.quantity_raw for r in records
        if r.energy_type == EnergyType.reactive
    ]

    total_grid = sum(grid_import_kwh)
    total_selfgen = sum(selfgen_kwh)
    total_gas_kwh = sum(gas_kwh)
    total_kwh = total_grid + total_selfgen + total_gas_kwh
    total_co2_kg = sum(e.co2_kg for e in co2_estimates)

    # Energy baseline: rolling average of monthly grid consumption
    n_months = len(grid_import_kwh)
    enb = (total_grid / n_months) if n_months > 0 else 0.0

    # EnPI: actual vs baseline
    ref = baseline_kwh_per_month if baseline_kwh_per_month else enb
    enpi = round(enb / ref, 3) if ref and ref > 0 else None

    # Dependency and self-sufficiency
    grid_dependency = round(total_grid / total_kwh * 100, 1) if total_kwh > 0 else None
    self_sufficiency = round(total_selfgen / total_kwh * 100, 1) if total_kwh > 0 else None

    # Power factor
    total_reactive = sum(reactive_kvarh)
    if total_grid > 0 and total_reactive > 0:
        apparent = math.sqrt(total_grid ** 2 + total_reactive ** 2)
        power_factor = round(total_grid / apparent, 3)
    else:
        power_factor = None

    # CO2 intensity
    co2_intensity = round(total_co2_kg / total_kwh, 4) if total_kwh > 0 else None

    return {
        "enpi": enpi,
        "enb_kwh_per_month": round(enb, 1),
        "total_kwh": round(total_kwh, 1),
        "total_grid_kwh": round(total_grid, 1),
        "total_selfgen_kwh": round(total_selfgen, 1),
        "grid_dependency_pct": grid_dependency,
        "self_sufficiency_pct": self_sufficiency,
        "power_factor": power_factor,
        "total_co2_kg": round(total_co2_kg, 2),
        "co2_intensity_kg_per_kwh": co2_intensity,
        "record_count": len(records),
        "months_covered": n_months,
    }
