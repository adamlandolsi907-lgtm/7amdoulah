"""
NRTF Energy Pipeline — FastAPI application.

Routes:
  GET  /health
  POST /extract          body: {file_b64, file_type, filename}
  GET  /unified          ?from=YYYY-MM&to=YYYY-MM&energy_type=&zone=
  GET  /co2              ?from=&to=&scope=
  GET  /anomalies        ?recompute=false
  GET  /forecast         ?horizon=3&zone=global&energy_type=electricity
  GET  /kpis             ?from=&to=
  GET  /graph
  POST /submit
"""

import base64
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from app.db import store
from app.models.schemas import (
    CO2Estimate,
    EnergyRecord,
    EnergyType,
    SubmissionPayload,
)
from app.pipeline import co2 as co2_engine
from app.pipeline import anomaly as anomaly_engine
from app.pipeline import graph as graph_engine
from app.pipeline import kpis as kpi_engine
from app.pipeline.normalize import normalize_record

_DB = str(Path(__file__).parent.parent / "data" / "pipeline.db")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init_db(_DB)
    yield


app = FastAPI(
    title="NRTF Energy Pipeline API",
    description=(
        "Document extraction, unit normalization, CO2 estimation — "
        "Re·Tech Fusion Hackathon (INSAT)"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    return {"status": "ok", "db": _DB}


# ── Extract ───────────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    file_b64: str       # base64-encoded file content
    file_type: str      # "jpeg" | "pdf" | "xlsx"
    filename: str = "upload"


@app.post("/extract", tags=["pipeline"])
def extract(req: ExtractRequest):
    """
    Extract energy data from a base64-encoded document.
    Supported file_type values: jpeg, jpg, pdf, xlsx.
    Automatically normalises units and persists to DB.
    """
    try:
        file_bytes = base64.b64decode(req.file_b64)
    except Exception:
        raise HTTPException(400, "Invalid base64 payload")

    suffix_map = {
        "jpeg": ".jpeg", "jpg": ".jpeg",
        "pdf": ".pdf",
        "xlsx": ".xlsx", "xls": ".xlsx",
    }
    suffix = suffix_map.get(req.file_type.lower(), f".{req.file_type}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tf:
        tf.write(file_bytes)
        tmp_path = tf.name

    try:
        records = _run_extractor(tmp_path, req.file_type.lower())
    finally:
        os.unlink(tmp_path)

    results = []
    for rec in records:
        if isinstance(rec, EnergyRecord):
            normalize_record(rec)
            store.upsert_energy_record(rec, _DB)
            estimates = co2_engine.estimate_co2(rec)
            store.upsert_co2_estimates(estimates, _DB)
        else:
            # StegBillRecord / StegMeterReadingRecord — persist as-is
            store.upsert_energy_record(rec, _DB)
            estimates = co2_engine.estimate_co2(rec)
            store.upsert_co2_estimates(estimates, _DB)
        results.append(rec.model_dump())

    return {"extracted": len(results), "records": results}


def _run_extractor(path: str, file_type: str) -> list:
    if file_type in ("jpeg", "jpg"):
        from app.extractors.image import extract_image
        return [extract_image(path)]
    if file_type == "pdf":
        from app.extractors.pdf import extract_pdf
        return extract_pdf(path)
    if file_type in ("xlsx", "xls"):
        from app.extractors.excel import extract_excel
        return extract_excel(path)
    raise HTTPException(400, f"Unsupported file_type: '{file_type}'")


# ── Unified energy records ────────────────────────────────────────────────────

@app.get("/unified", tags=["data"])
def unified(
    from_date: Optional[str] = Query(None, alias="from", description="YYYY-MM"),
    to_date: Optional[str] = Query(None, alias="to",   description="YYYY-MM"),
    energy_type: Optional[str] = None,
    zone: Optional[str] = None,
):
    """Return normalised energy records, optionally filtered."""
    records = store.get_energy_records(_DB, from_date, to_date, energy_type, zone)
    return {"count": len(records), "records": records}


# ── CO2 estimates ─────────────────────────────────────────────────────────────

@app.get("/co2", tags=["data"])
def co2_view(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
    scope: Optional[str] = None,
):
    """Return CO2 estimates. scope: scope_1 | scope_2 | scope_2_credit"""
    estimates = store.get_co2_estimates(_DB, from_date, to_date, scope)
    total_kg = sum(e.get("co2_kg", 0) for e in estimates)
    return {
        "count": len(estimates),
        "total_co2_kg": round(total_kg, 2),
        "estimates": estimates,
    }


# ── Anomalies ─────────────────────────────────────────────────────────────────

@app.get("/anomalies", tags=["analytics"])
def anomalies(recompute: bool = False):
    """
    Return detected anomalies.
    Set recompute=true to re-run all 4 detectors against current DB data.
    """
    if recompute:
        raw = store.get_energy_records(_DB)
        all_recs = [EnergyRecord(**r) for r in raw
                    if r.get("document_type") and r.get("quantity_kwh")]
        excel_recs = [r for r in all_recs if r.document_type.value == "excel_report"]
        bill_recs  = [r for r in all_recs if r.document_type.value in ("steg_bill",)]
        detected = anomaly_engine.detect_all(all_recs, bill_records=bill_recs)
        store.upsert_anomalies(detected, _DB)

    return {"anomalies": store.get_anomalies(_DB)}


# ── Forecast ──────────────────────────────────────────────────────────────────

@app.get("/forecast", tags=["analytics"])
def forecast_view(
    horizon: int = Query(3, ge=1, le=12, description="Months ahead to forecast"),
    zone: str = "global",
    energy_type: str = "electricity",
):
    """Forecast energy consumption using Prophet (falls back to Holt-Winters)."""
    from app.pipeline.forecast import forecast

    raw = store.get_energy_records(_DB)
    recs = [EnergyRecord(**r) for r in raw if r.get("quantity_kwh")]

    try:
        etype = EnergyType(energy_type)
    except ValueError:
        raise HTTPException(400, f"Unknown energy_type: '{energy_type}'")

    result = forecast(recs, zone=zone, energy_type=etype, horizon=horizon)
    if result is None:
        raise HTTPException(404, "Insufficient data for forecast (need ≥ 4 data points)")
    return result.model_dump()


# ── KPIs ──────────────────────────────────────────────────────────────────────

@app.get("/kpis", tags=["analytics"])
def kpis(
    from_date: Optional[str] = Query(None, alias="from"),
    to_date: Optional[str] = Query(None, alias="to"),
):
    """Return ISO 50001 energy performance indicators."""
    raw_records = store.get_energy_records(_DB, from_date, to_date)
    raw_co2     = store.get_co2_estimates(_DB, from_date, to_date)

    recs      = [EnergyRecord(**r) for r in raw_records if r.get("quantity_kwh")]
    estimates = [CO2Estimate(**e) for e in raw_co2]

    return kpi_engine.compute_kpis(recs, estimates)


# ── Knowledge graph ───────────────────────────────────────────────────────────

@app.get("/graph", tags=["analytics"])
def graph_view():
    """Return the knowledge graph as {nodes, edges}."""
    raw_records = store.get_energy_records(_DB)
    raw_co2     = store.get_co2_estimates(_DB)

    recs      = [EnergyRecord(**r) for r in raw_records if r.get("quantity_kwh")]
    estimates = [CO2Estimate(**e) for e in raw_co2]

    G = graph_engine.build_graph(recs, estimates)
    return graph_engine.graph_to_dict(G)


# ── Submit ────────────────────────────────────────────────────────────────────

@app.post("/submit", tags=["submission"])
def submit():
    """Format and return submission payload for the challenge platform."""
    from app.models.schemas import Anomaly

    raw_records = store.get_energy_records(_DB)
    raw_co2     = store.get_co2_estimates(_DB)
    raw_anom    = store.get_anomalies(_DB)

    records   = [EnergyRecord(**r) for r in raw_records if r.get("quantity_kwh")]
    estimates = [CO2Estimate(**e) for e in raw_co2]
    anom_list = []
    for a in raw_anom:
        try:
            anom_list.append(Anomaly(**a))
        except Exception:
            pass

    payload = SubmissionPayload(
        team_id="NRTF",
        documents=records,
        co2_estimates=estimates,
        anomalies=anom_list,
    )
    return payload.model_dump()
