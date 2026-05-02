from pydantic import BaseModel, Field
from typing import Optional, Literal
from enum import Enum


class DocumentType(str, Enum):
    steg_bill = "steg_bill"
    steg_meter_reading = "steg_meter_reading"
    excel_report = "excel_report"
    pdf_invoice = "pdf_invoice"
    unknown = "unknown"


class EnergyType(str, Enum):
    electricity = "electricity"
    natural_gas = "natural_gas"
    steam = "steam"
    hot_water = "hot_water"
    chilled_water = "chilled_water"
    compressed_air = "compressed_air"
    reactive = "reactive"  # kVArh — not convertible to kWh


class GHGScope(str, Enum):
    scope_1 = "scope_1"   # direct combustion on-site
    scope_2 = "scope_2"   # purchased electricity
    scope_2_credit = "scope_2_credit"  # electricity sold back to grid


class AnomalyType(str, Enum):
    spike = "SPIKE"
    dropout = "DROPOUT"
    drift = "DRIFT"
    reconciliation = "RECONCILIATION"


# ── Extraction output ─────────────────────────────────────────────────────────

class EnergyRecord(BaseModel):
    document_id: str
    document_type: DocumentType
    source_file: str
    date: str                           # "YYYY-MM"
    supplier: Optional[str] = None
    site: Optional[str] = None
    zone: Optional[str] = "global"      # global | alpha | beta | gamma
    energy_type: EnergyType
    quantity_raw: float
    unit_raw: str
    quantity_kwh: Optional[float] = None
    conversion_factor: Optional[float] = None
    conversion_formula: Optional[str] = None
    extraction_confidence: float = 1.0
    extraction_method: str = "manual"


class StegBillRecord(BaseModel):
    """Structured output of a STEG Facture Moyenne Tension."""
    document_id: str
    source_file: str
    date: str                           # "YYYY-MM"
    facture_number: Optional[str] = None
    active_energy_kwh: Optional[float] = None
    reactive_energy_kvarh: Optional[float] = None
    power_subscribed_kva: Optional[float] = None
    amount_tnd: Optional[float] = None
    supplier: str = "STEG"
    site: Optional[str] = None
    district: Optional[str] = None
    extraction_confidence: float = 1.0
    extraction_method: str = "claude_vision"


class StegMeterReadingRecord(BaseModel):
    """Structured output of a STEG Fiche Relevé Énergie Achat et Vente."""
    document_id: str
    source_file: str
    date: str
    client_ref: Optional[str] = None
    purchase_jour_kwh: Optional[float] = None
    purchase_pointe_kwh: Optional[float] = None
    purchase_nuit_kwh: Optional[float] = None
    purchase_soir_kwh: Optional[float] = None
    purchase_reactive_kvarh: Optional[float] = None
    injection_jour_kwh: Optional[float] = None
    injection_pointe_kwh: Optional[float] = None
    injection_nuit_kwh: Optional[float] = None
    injection_soir_kwh: Optional[float] = None
    net_consumption_kwh: Optional[float] = None
    max_demand_j_kva: Optional[float] = None
    max_demand_p_kva: Optional[float] = None
    max_demand_s_kva: Optional[float] = None
    extraction_confidence: float = 1.0
    extraction_method: str = "claude_vision"


# ── CO2 output ────────────────────────────────────────────────────────────────

class CO2Estimate(BaseModel):
    record_id: str
    date: str
    scope: GHGScope
    energy_type: EnergyType
    quantity_kwh: float
    emission_factor: float              # kgCO2/kWh
    co2_kg: float
    zone: Optional[str] = "global"
    note: Optional[str] = None


# ── Anomaly output ────────────────────────────────────────────────────────────

class Anomaly(BaseModel):
    anomaly_id: str
    type: AnomalyType
    date: str
    meter_or_site: str
    value_observed: Optional[float] = None
    value_expected: Optional[float] = None
    delta_pct: Optional[float] = None
    confidence_score: float
    document_source: Optional[str] = None
    description: str


# ── Forecast output ───────────────────────────────────────────────────────────

class ForecastPoint(BaseModel):
    date: str
    predicted_kwh: float
    lower_bound: float
    upper_bound: float


class ForecastResult(BaseModel):
    model_config = {"protected_namespaces": ()}

    zone: str
    energy_type: EnergyType
    horizon_months: int
    points: list[ForecastPoint]
    model_used: str


# ── Submission format (challenge platform) ────────────────────────────────────

class SubmissionPayload(BaseModel):
    team_id: str = "NRTF"
    documents: list[EnergyRecord]
    co2_estimates: list[CO2Estimate]
    anomalies: list[Anomaly] = Field(default_factory=list)
