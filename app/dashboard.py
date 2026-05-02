"""
NRTF Energy Dashboard — Streamlit UI.

Sections:
  1. KPI Cards        — ISO 50001 indicators
  2. Energy Timeline  — monthly consumption by energy type
  3. CO2 Overview     — scope breakdown + simple vs tri-gen toggle
  4. Anomalies        — detected data quality issues
  5. Forecast         — 3-month ahead prediction
  6. Knowledge Graph  — interactive pyvis visualization
"""

import os
from pathlib import Path

import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="NRTF Energy Dashboard — ADWYA",
    page_icon="⚡",
    layout="wide",
)

# ── DB path ───────────────────────────────────────────────────────────────────

_DB = str(Path(__file__).parent.parent / "data" / "pipeline.db")


@st.cache_data(ttl=60)
def _load_records(db_path: str):
    from app.db.store import get_energy_records, init_db
    init_db(db_path)
    return get_energy_records(db_path)


@st.cache_data(ttl=60)
def _load_co2(db_path: str):
    from app.db.store import get_co2_estimates
    return get_co2_estimates(db_path)


@st.cache_data(ttl=60)
def _load_anomalies(db_path: str):
    from app.db.store import get_anomalies
    return get_anomalies(db_path)


# ── Load data ─────────────────────────────────────────────────────────────────

st.title("⚡ NRTF Energy Intelligence Dashboard")
st.caption("Société ADWYA · Pharmaceutical Factory · Sidi Daoud, Tunisia")

raw_records  = _load_records(_DB)
raw_co2      = _load_co2(_DB)
raw_anomalies = _load_anomalies(_DB)

if not raw_records:
    st.warning(
        "No data in the database yet. "
        "Run the extraction pipeline first: "
        "`python -m scripts.run_pipeline`"
    )
    st.stop()

# Parse into Pydantic
from app.models.schemas import CO2Estimate, EnergyRecord, EnergyType

try:
    records   = [EnergyRecord(**r) for r in raw_records if r.get("quantity_kwh")]
    estimates = [CO2Estimate(**e) for e in raw_co2]
except Exception as exc:
    st.error(f"Data parse error: {exc}")
    st.stop()

# ── KPIs ──────────────────────────────────────────────────────────────────────

from app.pipeline.kpis import compute_kpis
kpis = compute_kpis(records, estimates)

st.subheader("📊 ISO 50001 Key Performance Indicators")

c1, c2, c3, c4, c5 = st.columns(5)

def _fmt(val, suffix="", precision=1):
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.{precision}f}{suffix}"
    return f"{val}{suffix}"

c1.metric("Total Energy", _fmt(kpis["total_kwh"] / 1000, " MWh"))
c2.metric("Self-Sufficiency", _fmt(kpis["self_sufficiency_pct"], "%"))
c3.metric("Grid Dependency", _fmt(kpis["grid_dependency_pct"], "%"))
c4.metric("Power Factor", _fmt(kpis["power_factor"], "", 3))
c5.metric("CO₂ Intensity", _fmt(kpis["co2_intensity_kg_per_kwh"], " kgCO₂/kWh", 4))

st.divider()

# ── Energy Timeline ───────────────────────────────────────────────────────────

import pandas as pd

st.subheader("⚡ Monthly Energy Consumption")

rec_rows = [
    {
        "date": r.date,
        "energy_type": r.energy_type.value,
        "zone": r.zone or "global",
        "kwh": r.quantity_kwh,
    }
    for r in records
]
df = pd.DataFrame(rec_rows)

if not df.empty:
    col_tab, col_filter = st.columns([3, 1])
    with col_filter:
        selected_types = st.multiselect(
            "Energy type",
            options=df["energy_type"].unique().tolist(),
            default=df["energy_type"].unique().tolist(),
        )
    df_filtered = df[df["energy_type"].isin(selected_types)]
    pivot = df_filtered.pivot_table(
        index="date", columns="energy_type", values="kwh", aggfunc="sum"
    ).fillna(0)
    st.bar_chart(pivot)
else:
    st.info("No energy records to chart.")

st.divider()

# ── CO2 Overview ──────────────────────────────────────────────────────────────

st.subheader("🌿 CO₂ Emissions Overview")

co2_mode = st.radio(
    "Calculation mode",
    ["Simple (per-record)", "Tri-gen Adjusted"],
    horizontal=True,
)

co2_rows = [
    {
        "date": e.date,
        "scope": e.scope.value,
        "co2_kg": e.co2_kg,
        "energy_type": e.energy_type.value,
    }
    for e in estimates
]
df_co2 = pd.DataFrame(co2_rows) if co2_rows else pd.DataFrame()

if co2_mode == "Tri-gen Adjusted" and not df_co2.empty:
    # Re-compute tri-gen breakdown using records from DB
    from app.pipeline.co2 import trigen_co2_breakdown
    gas_recs = [r for r in records if r.energy_type == EnergyType.natural_gas]
    elec_self = [r for r in records if r.energy_type == EnergyType.electricity
                 and r.zone == "self_generation"]
    if gas_recs:
        gas_nm3_total = sum(r.quantity_raw for r in gas_recs
                            if r.unit_raw.lower().startswith("nm"))
        elec_kwh = sum(r.quantity_kwh for r in elec_self if r.quantity_kwh)
        breakdown = trigen_co2_breakdown(
            gas_nm3=gas_nm3_total,
            electricity_produced_kwh=elec_kwh,
            heat_recovered_kwh=0.0,
            cooling_kwh=0.0,
        )
        b_col1, b_col2, b_col3, b_col4 = st.columns(4)
        b_col1.metric("Gross CO₂ (gas)", f"{breakdown['gross_co2_kg']:.0f} kg")
        b_col2.metric("Avoided (electricity)", f"{breakdown['avoided_electricity_kg']:.0f} kg")
        b_col3.metric("Avoided (heat)", f"{breakdown['avoided_heat_kg']:.0f} kg")
        b_col4.metric("Net CO₂", f"{breakdown['net_co2_kg']:.0f} kg",
                      delta=f"{breakdown['net_co2_kg'] - breakdown['gross_co2_kg']:.0f} kg")
        st.caption(
            "Tri-gen net can be negative when electricity production avoids "
            "more grid CO₂ than gas combustion emits."
        )

if not df_co2.empty:
    pivot_co2 = df_co2.pivot_table(
        index="date", columns="scope", values="co2_kg", aggfunc="sum"
    ).fillna(0)
    st.bar_chart(pivot_co2)
    st.metric(
        "Total CO₂ (all scopes)",
        f"{df_co2['co2_kg'].sum():.0f} kg",
        help="Scope 2 credit (grid injection) appears as negative values.",
    )
else:
    st.info("No CO₂ estimates available.")

st.divider()

# ── Anomalies ─────────────────────────────────────────────────────────────────

st.subheader("🚨 Anomaly Detection")

anom_col1, anom_col2 = st.columns([4, 1])
with anom_col2:
    if st.button("Re-run detectors"):
        from app.pipeline.anomaly import detect_all
        from app.db.store import upsert_anomalies
        excel_recs = [r for r in records if r.document_type.value == "excel_report"]
        bill_recs  = [r for r in records if r.document_type.value == "steg_bill"]
        detected = detect_all(records, bill_records=bill_recs)
        upsert_anomalies(detected, _DB)
        st.cache_data.clear()
        st.rerun()

if raw_anomalies:
    df_anom = pd.DataFrame(raw_anomalies)
    cols_show = ["date", "type", "meter_or_site", "value_observed",
                 "value_expected", "delta_pct", "confidence_score", "description"]
    cols_show = [c for c in cols_show if c in df_anom.columns]
    st.dataframe(df_anom[cols_show], use_container_width=True)
    st.caption(f"{len(raw_anomalies)} anomalies detected")
else:
    st.info("No anomalies detected. Click 'Re-run detectors' to analyse current data.")

st.divider()

# ── Forecast ──────────────────────────────────────────────────────────────────

st.subheader("📈 Energy Forecast")

fc_col1, fc_col2 = st.columns([1, 3])
with fc_col1:
    horizon = st.slider("Forecast horizon (months)", 1, 6, 3)
    fc_zone = st.selectbox("Zone", ["global", "grid_import", "self_generation"])

from app.pipeline.forecast import forecast as run_forecast

fc_result = run_forecast(records, zone=fc_zone, horizon=horizon)
if fc_result:
    fc_df = pd.DataFrame([p.model_dump() for p in fc_result.points])
    fc_df = fc_df.set_index("date")
    with fc_col2:
        st.line_chart(fc_df[["predicted_kwh", "lower_bound", "upper_bound"]])
        st.caption(f"Model: {fc_result.model_used} | "
                   f"Warning: confidence intervals are wide (~12 data points)")
else:
    with fc_col2:
        st.info("Insufficient data for forecast (need ≥ 4 monthly records for this zone).")

st.divider()

# ── Knowledge Graph ───────────────────────────────────────────────────────────

st.subheader("🔗 Energy Knowledge Graph")

with st.expander("Show graph", expanded=False):
    from app.pipeline.graph import build_graph, render_graph_html
    G = build_graph(records, estimates)
    st.caption(
        f"Nodes: {G.number_of_nodes()} · Edges: {G.number_of_edges()}"
    )
    html = render_graph_html(G, height="480px")
    st.components.v1.html(html, height=490, scrolling=True)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown(
    """
    ---
    **NRTF Team** · Re·Tech Fusion Hackathon · INSAT
    Factory: Société ADWYA · Data range: Aug 2025 – Jul 2026
    """
)
