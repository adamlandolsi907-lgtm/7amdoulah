"""
SQLite storage layer — persists all pipeline outputs to a local DB.

Tables:
  energy_records  — extracted + normalized energy readings
  co2_estimates   — GHG emissions per record
  anomalies       — detected anomalies
  forecast_points — Prophet forecast output

All records are stored as JSON blobs (Pydantic .model_dump()) for simplicity.
Primary key = document_id / anomaly_id / composite key where applicable.
"""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.models.schemas import (
    Anomaly,
    CO2Estimate,
    EnergyRecord,
    ForecastResult,
    StegBillRecord,
    StegMeterReadingRecord,
)

AnyEnergyRecord = EnergyRecord | StegBillRecord | StegMeterReadingRecord

_DEFAULT_DB = Path(__file__).parent.parent.parent / "data" / "pipeline.db"

_DDL = """
CREATE TABLE IF NOT EXISTS energy_records (
    document_id   TEXT PRIMARY KEY,
    document_type TEXT,
    source_file   TEXT,
    date          TEXT,
    energy_type   TEXT,
    quantity_kwh  REAL,
    unit_raw      TEXT,
    zone          TEXT,
    supplier      TEXT,
    confidence    REAL,
    payload       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS co2_estimates (
    record_id   TEXT,
    date        TEXT,
    scope       TEXT,
    co2_kg      REAL,
    payload     TEXT NOT NULL,
    PRIMARY KEY (record_id, scope)
);

CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id   TEXT PRIMARY KEY,
    type         TEXT,
    date         TEXT,
    confidence   REAL,
    payload      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS forecast_points (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    zone        TEXT,
    energy_type TEXT,
    date        TEXT,
    predicted   REAL,
    lower       REAL,
    upper       REAL
);
"""


@contextmanager
def _conn(db_path: str):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(db_path: str = str(_DEFAULT_DB)) -> None:
    """Create tables if they don't exist."""
    with _conn(db_path) as con:
        con.executescript(_DDL)


# ── Energy records ────────────────────────────────────────────────────────────

def upsert_energy_record(record: AnyEnergyRecord, db_path: str = str(_DEFAULT_DB)) -> None:
    doc_id    = record.document_id
    doc_type  = getattr(record, "document_type", None)
    if doc_type is not None:
        doc_type = doc_type.value if hasattr(doc_type, "value") else str(doc_type)
    source    = record.source_file
    date      = record.date
    e_type    = getattr(record, "energy_type", None)
    e_type    = e_type.value if hasattr(e_type, "value") else str(e_type) if e_type else None
    kwh       = getattr(record, "quantity_kwh", None)
    unit      = getattr(record, "unit_raw", "kWh")
    zone      = getattr(record, "zone", "global")
    supplier  = getattr(record, "supplier", None)
    conf      = getattr(record, "extraction_confidence", None)
    payload   = json.dumps(record.model_dump(), ensure_ascii=False, default=str)

    with _conn(db_path) as con:
        con.execute("""
            INSERT OR REPLACE INTO energy_records
              (document_id, document_type, source_file, date, energy_type,
               quantity_kwh, unit_raw, zone, supplier, confidence, payload)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (doc_id, doc_type, source, date, e_type, kwh, unit, zone, supplier, conf, payload))


def upsert_energy_records(records: list[AnyEnergyRecord], db_path: str = str(_DEFAULT_DB)) -> None:
    for r in records:
        upsert_energy_record(r, db_path)


def get_energy_records(
    db_path: str = str(_DEFAULT_DB),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    energy_type: Optional[str] = None,
    zone: Optional[str] = None,
) -> list[dict]:
    """Query energy records; returns list of raw dicts (payload deserialized)."""
    clauses, params = [], []
    if date_from:
        clauses.append("date >= ?"); params.append(date_from)
    if date_to:
        clauses.append("date <= ?"); params.append(date_to)
    if energy_type:
        clauses.append("energy_type = ?"); params.append(energy_type)
    if zone:
        clauses.append("zone = ?"); params.append(zone)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT payload FROM energy_records {where} ORDER BY date"
    with _conn(db_path) as con:
        rows = con.execute(sql, params).fetchall()
    return [json.loads(r["payload"]) for r in rows]


# ── CO2 estimates ─────────────────────────────────────────────────────────────

def upsert_co2_estimate(est: CO2Estimate, db_path: str = str(_DEFAULT_DB)) -> None:
    payload = json.dumps(est.model_dump(), ensure_ascii=False, default=str)
    with _conn(db_path) as con:
        con.execute("""
            INSERT OR REPLACE INTO co2_estimates (record_id, date, scope, co2_kg, payload)
            VALUES (?,?,?,?,?)
        """, (est.record_id, est.date, est.scope.value, est.co2_kg, payload))


def upsert_co2_estimates(estimates: list[CO2Estimate], db_path: str = str(_DEFAULT_DB)) -> None:
    for e in estimates:
        upsert_co2_estimate(e, db_path)


def get_co2_estimates(
    db_path: str = str(_DEFAULT_DB),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    scope: Optional[str] = None,
) -> list[dict]:
    clauses, params = [], []
    if date_from:
        clauses.append("date >= ?"); params.append(date_from)
    if date_to:
        clauses.append("date <= ?"); params.append(date_to)
    if scope:
        clauses.append("scope = ?"); params.append(scope)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"SELECT payload FROM co2_estimates {where} ORDER BY date"
    with _conn(db_path) as con:
        rows = con.execute(sql, params).fetchall()
    return [json.loads(r["payload"]) for r in rows]


# ── Anomalies ─────────────────────────────────────────────────────────────────

def upsert_anomaly(anomaly: Anomaly, db_path: str = str(_DEFAULT_DB)) -> None:
    payload = json.dumps(anomaly.model_dump(), ensure_ascii=False, default=str)
    with _conn(db_path) as con:
        con.execute("""
            INSERT OR REPLACE INTO anomalies (anomaly_id, type, date, confidence, payload)
            VALUES (?,?,?,?,?)
        """, (anomaly.anomaly_id, anomaly.type.value, anomaly.date,
              anomaly.confidence_score, payload))


def upsert_anomalies(anomalies: list[Anomaly], db_path: str = str(_DEFAULT_DB)) -> None:
    for a in anomalies:
        upsert_anomaly(a, db_path)


def get_anomalies(db_path: str = str(_DEFAULT_DB)) -> list[dict]:
    with _conn(db_path) as con:
        rows = con.execute("SELECT payload FROM anomalies ORDER BY date").fetchall()
    return [json.loads(r["payload"]) for r in rows]


# ── Forecast ──────────────────────────────────────────────────────────────────

def upsert_forecast(result: ForecastResult, db_path: str = str(_DEFAULT_DB)) -> None:
    e_type = result.energy_type.value
    with _conn(db_path) as con:
        con.execute(
            "DELETE FROM forecast_points WHERE zone=? AND energy_type=?",
            (result.zone, e_type),
        )
        con.executemany("""
            INSERT INTO forecast_points (zone, energy_type, date, predicted, lower, upper)
            VALUES (?,?,?,?,?,?)
        """, [
            (result.zone, e_type, p.date, p.predicted_kwh, p.lower_bound, p.upper_bound)
            for p in result.points
        ])


def get_forecast(
    zone: str = "global",
    energy_type: str = "electricity",
    db_path: str = str(_DEFAULT_DB),
) -> list[dict]:
    with _conn(db_path) as con:
        rows = con.execute("""
            SELECT date, predicted, lower, upper FROM forecast_points
            WHERE zone=? AND energy_type=? ORDER BY date
        """, (zone, energy_type)).fetchall()
    return [dict(r) for r in rows]
