"""
Unit normalization engine.
Canonical output unit: kWh.

All factors are HHV (High Heating Value) by default.
Gas units expose both HHV and LHV — use LHV for CO2 combustion calculations.
"""

from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.schemas import EnergyRecord

# ── Conversion table ──────────────────────────────────────────────────────────
# (unit_raw_lowercase) → (factor_to_kwh, formula_description)

CONVERSION_TABLE: dict[str, tuple[float, str]] = {
    # Electrical
    "kwh":   (1.0,        "identity"),
    "mwh":   (1000.0,     "×1000"),
    "gwh":   (1_000_000.0,"×1,000,000"),

    # Thermal — SI
    "gj":    (277.778,    "1 GJ / 3.6 MJ·kWh⁻¹"),
    "mj":    (0.27778,    "1 MJ / 3.6"),
    "kj":    (0.000278,   "1 kJ / 3600"),

    # Thermal — caloric
    "gcal":  (1163.0,     "1 Gcal = 1000 kcal × 1.163 kWh·kcal⁻¹"),
    "mcal":  (1.163,      "1 Mcal = 1 thermie"),
    "kcal":  (0.001163,   "1 kcal = 0.001163 kWh"),
    "th":    (1.163,      "thermie = 1 Mcal"),     # Tunisian gas billing unit
    "therm": (29.3071,    "1 therm (US) = 29.307 kWh"),

    # Thermal — imperial
    "btu":   (0.000293071,"NIST exact"),
    "mmbtu": (293.071,    "1 MMBtu = 1,000,000 BTU"),

    # Mass-energy
    "toe":   (11630.0,    "IEA: 1 toe = 10 Gcal HHV"),
    "toe_lhv": (10000.0,  "1 toe LHV = 10,000 kWh"),
    "kgoe":  (11.63,      "1 kgoe = 11.63 kWh"),

    # Gas volumetric — Tunisia STEG PCS
    "nm3":   (10.55,      "STEG PCS Tunisia ≈ 10.55 kWh/Nm³ HHV"),
    "nm³":   (10.55,      "STEG PCS Tunisia ≈ 10.55 kWh/Nm³ HHV"),
    "m3":    (10.55,      "assumed Nm³ at standard conditions"),

    # Steam — saturated at factory operating pressure (5 bar)
    "t_vapeur": (681.0,   "sat. steam 5 bar: h=2748 kJ/kg ÷ 3.6"),
    "t vapeur": (681.0,   "sat. steam 5 bar: h=2748 kJ/kg ÷ 3.6"),
    "t":        (681.0,   "assumed saturated steam at 5 bar"),
    "tonne_vapeur": (681.0, "sat. steam 5 bar"),
}

# Gas LHV factor for CO2 combustion (lower heating value)
GAS_LHV_FACTOR = 9.51  # kWh/Nm³ — use this for CO2 calculations only

# Units that must NOT be converted to kWh
NON_CONVERTIBLE = {"kvarh", "kvar", "var", "mvarh"}


def normalize(quantity: float, unit_raw: str) -> tuple[Optional[float], float, str]:
    """
    Convert a quantity to kWh.

    Returns:
        (quantity_kwh, conversion_factor, formula)
        quantity_kwh is None if the unit is non-convertible (e.g. kVArh).
    """
    unit = unit_raw.strip().lower()

    if unit in NON_CONVERTIBLE:
        return None, 0.0, f"non-convertible unit: {unit_raw}"

    entry = CONVERSION_TABLE.get(unit)
    if entry is None:
        # Try stripping whitespace variants
        for key in CONVERSION_TABLE:
            if key.replace(" ", "") == unit.replace(" ", ""):
                entry = CONVERSION_TABLE[key]
                break

    if entry is None:
        raise ValueError(f"Unknown unit: '{unit_raw}'. Add it to CONVERSION_TABLE.")

    factor, formula = entry
    return round(quantity * factor, 6), factor, formula


def normalize_record(record: "EnergyRecord") -> "EnergyRecord":
    """
    Mutate an EnergyRecord in-place: populate quantity_kwh, conversion_factor,
    conversion_formula from quantity_raw + unit_raw.
    """
    try:
        kwh, factor, formula = normalize(record.quantity_raw, record.unit_raw)
        record.quantity_kwh = kwh
        record.conversion_factor = factor
        record.conversion_formula = formula
    except ValueError as e:
        record.quantity_kwh = None
        record.conversion_factor = None
        record.conversion_formula = f"ERROR: {e}"
    return record


def gas_kwh_lhv(quantity_nm3: float) -> float:
    """Return LHV-based kWh for natural gas — use for CO2 calculations."""
    return quantity_nm3 * GAS_LHV_FACTOR


def supported_units() -> list[str]:
    return sorted(CONVERSION_TABLE.keys())
