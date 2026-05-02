"""
Anomaly detection — 4 detectors for energy data quality monitoring.

Detectors:
  1. DROPOUT        — value is None or 0.0
  2. SPIKE          — Z-score on 3-month rolling window (|z| > 3.0)
  3. DRIFT          — linear regression slope > 10%/month over last 6 months
  4. RECONCILIATION — Excel grid_import vs STEG bill discrepancy (> 2%)
"""

import statistics
import uuid
from collections import defaultdict
from typing import Optional

from app.models.schemas import Anomaly, AnomalyType, EnergyRecord


# ── Detector 1: Dropout ───────────────────────────────────────────────────────

def detect_dropout(records: list[EnergyRecord]) -> list[Anomaly]:
    """Flag records where quantity_kwh is None or 0."""
    anomalies = []
    for rec in records:
        if rec.quantity_kwh is None or rec.quantity_kwh == 0.0:
            anomalies.append(Anomaly(
                anomaly_id=f"anom_do_{uuid.uuid4().hex[:8]}",
                type=AnomalyType.dropout,
                date=rec.date,
                meter_or_site=rec.zone or "global",
                value_observed=rec.quantity_kwh,
                value_expected=None,
                delta_pct=None,
                confidence_score=1.0,
                document_source=rec.source_file,
                description=f"Zero or null reading in {rec.source_file}",
            ))
    return anomalies


# ── Detector 2: Spike ─────────────────────────────────────────────────────────

def detect_spikes(
    records: list[EnergyRecord],
    z_threshold: float = 3.0,
) -> list[Anomaly]:
    """Z-score spike detection using 3-month rolling window per (zone, energy_type)."""
    groups: dict = defaultdict(list)
    for rec in records:
        key = (rec.zone or "global", rec.energy_type.value)
        if rec.quantity_kwh is not None and rec.quantity_kwh > 0:
            groups[key].append(rec)

    anomalies = []
    for key, group in groups.items():
        sorted_g = sorted(group, key=lambda r: r.date)
        values = [r.quantity_kwh for r in sorted_g]

        if len(values) < 4:
            continue

        for i in range(3, len(sorted_g)):
            window = values[max(0, i - 3):i]
            if len(window) < 2:
                continue
            mean = statistics.mean(window)
            stdev = statistics.stdev(window)
            if stdev == 0:
                continue
            z = (values[i] - mean) / stdev
            if abs(z) > z_threshold:
                rec = sorted_g[i]
                delta_pct = round(abs((values[i] - mean) / mean) * 100, 1) if mean else None
                anomalies.append(Anomaly(
                    anomaly_id=f"anom_sp_{uuid.uuid4().hex[:8]}",
                    type=AnomalyType.spike,
                    date=rec.date,
                    meter_or_site=f"{key[0]}/{key[1]}",
                    value_observed=round(values[i], 2),
                    value_expected=round(mean, 2),
                    delta_pct=delta_pct,
                    confidence_score=min(abs(z) / 5.0, 1.0),
                    document_source=rec.source_file,
                    description=f"Spike Z={z:.2f} vs 3-month window mean {mean:.1f} kWh",
                ))
    return anomalies


# ── Detector 3: Drift ─────────────────────────────────────────────────────────

def detect_drift(
    records: list[EnergyRecord],
    pct_threshold: float = 0.10,
) -> list[Anomaly]:
    """Linear regression drift > 10%/month over last 6 months per (zone, energy_type)."""
    groups: dict = defaultdict(list)
    for rec in records:
        key = (rec.zone or "global", rec.energy_type.value)
        if rec.quantity_kwh is not None and rec.quantity_kwh > 0:
            groups[key].append(rec)

    anomalies = []
    for key, group in groups.items():
        sorted_g = sorted(group, key=lambda r: r.date)
        last6 = sorted_g[-6:]
        if len(last6) < 4:
            continue

        y = [r.quantity_kwh for r in last6]
        x = list(range(len(y)))
        n = len(x)

        mean_x = statistics.mean(x)
        mean_y = statistics.mean(y)
        ss_xy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        ss_xx = sum((xi - mean_x) ** 2 for xi in x)

        if ss_xx == 0 or mean_y == 0:
            continue

        slope = ss_xy / ss_xx
        pct_change = slope / mean_y

        ss_tot = sum((v - mean_y) ** 2 for v in y)
        if ss_tot > 0:
            ss_res = sum((y[i] - (mean_y + slope * (x[i] - mean_x))) ** 2 for i in range(n))
            r2 = max(0.0, 1.0 - ss_res / ss_tot)
        else:
            r2 = 0.0

        if abs(pct_change) > pct_threshold:
            direction = "upward" if slope > 0 else "downward"
            anomalies.append(Anomaly(
                anomaly_id=f"anom_dr_{uuid.uuid4().hex[:8]}",
                type=AnomalyType.drift,
                date=last6[-1].date,
                meter_or_site=f"{key[0]}/{key[1]}",
                value_observed=round(slope, 3),
                value_expected=0.0,
                delta_pct=round(abs(pct_change) * 100, 1),
                confidence_score=round(r2, 3),
                document_source=last6[-1].source_file,
                description=(
                    f"Trend {direction}: {abs(pct_change)*100:.1f}%/month "
                    f"over last {n} months (R²={r2:.2f})"
                ),
            ))
    return anomalies


# ── Detector 4: Reconciliation ────────────────────────────────────────────────

def detect_reconciliation(
    excel_records: list[EnergyRecord],
    bill_records: list[EnergyRecord],
    tolerance_pct: float = 0.02,
) -> list[Anomaly]:
    """Compare Excel grid_import vs STEG bill kWh for the same month."""
    excel_by_date = {
        rec.date: rec
        for rec in excel_records
        if rec.zone == "grid_import"
        and rec.energy_type.value == "electricity"
        and rec.quantity_kwh
    }
    bill_by_date = {
        rec.date: rec
        for rec in bill_records
        if rec.energy_type.value == "electricity" and rec.quantity_kwh
    }

    anomalies = []
    for date, excel_rec in excel_by_date.items():
        if date not in bill_by_date:
            continue
        bill_rec = bill_by_date[date]
        excel_kwh = excel_rec.quantity_kwh or 0
        bill_kwh = bill_rec.quantity_kwh or 0
        if bill_kwh == 0:
            continue
        delta_pct = abs(excel_kwh - bill_kwh) / bill_kwh
        if delta_pct > tolerance_pct:
            anomalies.append(Anomaly(
                anomaly_id=f"anom_rc_{uuid.uuid4().hex[:8]}",
                type=AnomalyType.reconciliation,
                date=date,
                meter_or_site="CTR_3738835",
                value_observed=round(excel_kwh, 2),
                value_expected=round(bill_kwh, 2),
                delta_pct=round(delta_pct * 100, 1),
                confidence_score=round(min(1.0, delta_pct * 10), 3),
                document_source=f"{excel_rec.source_file} vs {bill_rec.source_file}",
                description=(
                    f"Excel {excel_kwh:.0f} kWh vs STEG bill "
                    f"{bill_kwh:.0f} kWh ({delta_pct*100:.1f}% discrepancy)"
                ),
            ))
    return anomalies


# ── Public API ────────────────────────────────────────────────────────────────

def detect_all(
    records: list[EnergyRecord],
    bill_records: Optional[list[EnergyRecord]] = None,
) -> list[Anomaly]:
    """Run all 4 detectors and return combined anomaly list."""
    result: list[Anomaly] = []
    result.extend(detect_dropout(records))
    result.extend(detect_spikes(records))
    result.extend(detect_drift(records))
    if bill_records:
        result.extend(detect_reconciliation(records, bill_records))
    return result
