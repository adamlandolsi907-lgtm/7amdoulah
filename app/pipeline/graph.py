"""
Energy knowledge graph — networkx + pyvis.

Node types : Site, Zone, Equipment, Supplier, Meter, EnergyReading, EmissionEstimate
Edge labels: SUPPLIES, PART_OF, LOCATED_IN, MEASURES, MEASURED_AT,
             MEASURED_BY, COMPUTED_FROM
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from app.models.schemas import CO2Estimate, EnergyRecord

# ── Static factory topology ───────────────────────────────────────────────────

_FACTORY_NODES: list[tuple[str, dict]] = [
    ("ADWYA",           {"type": "Site",     "address": "Sidi Daoud, Tunisia", "sector": "pharma"}),
    ("Zone_Alpha",      {"type": "Zone"}),
    ("Zone_Beta",       {"type": "Zone"}),
    ("Zone_Gamma",      {"type": "Zone"}),
    ("STEG",            {"type": "Supplier", "energy": "electricity+gas"}),
    ("Trigeneration",   {"type": "Equipment", "power_kw": 1200, "eff_pct": 43}),
    ("Boiler_Alpha",    {"type": "Equipment", "power_kw": 1240, "fuel": "gas"}),
    ("Boiler_Gamma",    {"type": "Equipment", "power_kw": 600,  "fuel": "gas"}),
    ("Chiller_GEG",     {"type": "Equipment", "power_kw": 2650, "type_cool": "electric"}),
    ("Chiller_THERMAX", {"type": "Equipment", "power_kw": 802,  "type_cool": "absorption"}),
    ("Meter_CTR3738835",{"type": "Meter",     "description": "STEG purchase meter"}),
]

_FACTORY_EDGES: list[tuple[str, str, dict]] = [
    ("STEG",         "ADWYA",       {"rel": "SUPPLIES"}),
    ("Zone_Alpha",   "ADWYA",       {"rel": "PART_OF"}),
    ("Zone_Beta",    "ADWYA",       {"rel": "PART_OF"}),
    ("Zone_Gamma",   "ADWYA",       {"rel": "PART_OF"}),
    ("Trigeneration","ADWYA",       {"rel": "LOCATED_IN"}),
    ("Boiler_Alpha", "Zone_Alpha",  {"rel": "LOCATED_IN"}),
    ("Boiler_Gamma", "Zone_Gamma",  {"rel": "LOCATED_IN"}),
    ("Chiller_GEG",  "ADWYA",       {"rel": "LOCATED_IN"}),
    ("Chiller_THERMAX","ADWYA",     {"rel": "LOCATED_IN"}),
    ("Meter_CTR3738835", "ADWYA",   {"rel": "MEASURES"}),
]

_ZONE_NODE_MAP = {
    "alpha": "Zone_Alpha",
    "beta": "Zone_Beta",
    "gamma": "Zone_Gamma",
    "grid_import": "ADWYA",
    "grid_export": "STEG",
    "self_generation": "Trigeneration",
    "global": "ADWYA",
}

_NODE_COLORS = {
    "Site":            "#e94560",
    "Zone":            "#16213e",
    "Equipment":       "#0f3460",
    "Supplier":        "#533483",
    "Meter":           "#2c3e50",
    "EnergyReading":   "#27ae60",
    "EmissionEstimate":"#e67e22",
}


def build_graph(
    records: list[EnergyRecord],
    co2_estimates: list[CO2Estimate],
) -> nx.DiGraph:
    """Build a directed knowledge graph from energy data."""
    G = nx.DiGraph()

    for name, attrs in _FACTORY_NODES:
        G.add_node(name, **attrs)
    for src, dst, attrs in _FACTORY_EDGES:
        G.add_edge(src, dst, **attrs)

    reading_ids: dict[str, str] = {}

    for rec in records:
        node_id = f"Rdg_{rec.document_id[:10]}"
        reading_ids[rec.document_id] = node_id
        G.add_node(
            node_id,
            type="EnergyReading",
            date=rec.date,
            energy_type=rec.energy_type.value,
            kwh=rec.quantity_kwh,
            zone=rec.zone or "global",
            source=rec.source_file,
        )
        zone_node = _ZONE_NODE_MAP.get(rec.zone or "global", "ADWYA")
        G.add_edge(node_id, zone_node, rel="MEASURED_AT")
        G.add_edge("Meter_CTR3738835", node_id, rel="MEASURED_BY")

    for est in co2_estimates:
        node_id = f"CO2_{est.record_id[:10]}_{est.scope.value}"
        G.add_node(
            node_id,
            type="EmissionEstimate",
            date=est.date,
            scope=est.scope.value,
            co2_kg=est.co2_kg,
        )
        reading_node = reading_ids.get(est.record_id)
        if reading_node and G.has_node(reading_node):
            G.add_edge(node_id, reading_node, rel="COMPUTED_FROM")

    return G


def graph_to_dict(G: nx.DiGraph) -> dict:
    """Export graph as {nodes, edges} JSON-serialisable dict."""
    return {
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [{"source": u, "target": v, **d} for u, v, d in G.edges(data=True)],
        "node_count": G.number_of_nodes(),
        "edge_count": G.number_of_edges(),
    }


def render_graph_html(G: nx.DiGraph, height: str = "500px") -> str:
    """Render the graph as an HTML string using pyvis."""
    try:
        import os
        import tempfile
        from pyvis.network import Network

        net = Network(
            height=height,
            width="100%",
            directed=True,
            bgcolor="#1a1a2e",
            font_color="white",
        )
        net.set_options("""
        {
          "edges": {"arrows": {"to": {"enabled": true}}},
          "physics": {"stabilization": {"iterations": 150}}
        }
        """)

        for node, data in G.nodes(data=True):
            ntype = data.get("type", "Unknown")
            color = _NODE_COLORS.get(ntype, "#7f8c8d")
            title = "<br>".join(f"{k}: {v}" for k, v in data.items())
            net.add_node(str(node), label=str(node), color=color, title=title)

        for u, v, data in G.edges(data=True):
            net.add_edge(str(u), str(v), title=data.get("rel", ""))

        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            net.save_graph(f.name)
            tmp_path = f.name

        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
        os.unlink(tmp_path)
        return html
    except Exception as exc:
        return f"<p style='color:red'>Graph rendering failed: {exc}</p>"
