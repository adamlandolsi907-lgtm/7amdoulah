import type { EnergyDocument, EnergyEdge, EnergyGraph, EnergyNode, EnergyType } from "./types";

const ENERGY_LABELS: Record<string, string> = {
  electricity: "Electricite",
  gas: "Gaz",
  natural_gas: "Gaz",
  steam: "Vapeur",
  hot_water: "Eau chaude",
  chilled_water: "Eau glacee",
  compressed_air: "Air comprime",
};

function energyLabel(t: EnergyType): string {
  return ENERGY_LABELS[t] ?? String(t);
}

function supplierFor(doc: EnergyDocument): string {
  return (doc.supplier || "Unknown").toUpperCase();
}

export function buildGraphFromDocuments(documents: EnergyDocument[]): EnergyGraph {
  const nodes: EnergyNode[] = [];
  const edges: EnergyEdge[] = [];

  nodes.push({
    id: "site_adwya",
    type: "site",
    label: "ADWYA",
    description: "Documents and energy records from Qdrant",
    position: { x: 520, y: 250 },
    severity: "ok",
  });

  const suppliers = [...new Set(documents.map((d) => supplierFor(d)))];
  suppliers.forEach((s, i) => {
    const sid = `supplier_${s.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;
    nodes.push({
      id: sid,
      type: "supplier",
      label: s,
      position: { x: 120, y: 120 + i * 120 },
      severity: "ok",
    });
    edges.push({
      id: `edge_${sid}_site`,
      source: sid,
      target: "site_adwya",
      type: "supplies",
      label: "source",
    });
  });

  const zoneNames = [...new Set(documents.map((d) => d.zone || "global"))];
  zoneNames.forEach((z, i) => {
    const zid = `zone_${z.toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;
    nodes.push({
      id: zid,
      type: "zone",
      label: `Zone ${z}`,
      position: { x: 420 + (i % 2) * 220, y: 80 + Math.floor(i / 2) * 360 },
      severity: "ok",
    });
    edges.push({
      id: `edge_${zid}_site`,
      source: zid,
      target: "site_adwya",
      type: "part_of",
    });
  });

  documents.forEach((doc, i) => {
    const docNodeId = `doc_${doc.id}`;
    const zoneId = `zone_${(doc.zone || "global").toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;
    const supplierId = `supplier_${supplierFor(doc).toLowerCase().replace(/[^a-z0-9]+/g, "_")}`;
    const yOffset = 80 + (i % 8) * 90;
    const xLane = 840 + Math.floor(i / 8) * 220;

    nodes.push({
      id: docNodeId,
      type: "document",
      label: doc.name,
      description: `${doc.date} | ${energyLabel(doc.energy_type)} | ${doc.quantity_kwh ?? "n/a"} kWh`,
      position: { x: xLane, y: yOffset },
      documentId: doc.id,
      severity: doc.anomalies.length ? "warning" : "ok",
      anomaly: doc.anomalies.length > 0,
    });

    edges.push({
      id: `edge_${docNodeId}_${zoneId}`,
      source: docNodeId,
      target: zoneId,
      type: "extracted_from",
      label: energyLabel(doc.energy_type),
    });

    if (nodes.some((n) => n.id === supplierId)) {
      edges.push({
        id: `edge_${docNodeId}_${supplierId}`,
        source: docNodeId,
        target: supplierId,
        type: "located_in",
      });
    }
  });

  return { nodes, edges };
}
