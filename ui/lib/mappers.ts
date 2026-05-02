import type { EnergyDocument, ExtractionMethod, ExtractedField } from "./types";
import { getDocumentTypeLabel } from "./utils";

type ApiRecord = Record<string, any>;

function inferDocType(record: ApiRecord): EnergyDocument["doc_type"] {
  if (record.document_type) {
    if (record.document_type === "pdf_invoice") return "pdf_report";
    return record.document_type;
  }
  if (record.facture_number || record.active_energy_kwh !== undefined) return "steg_bill";
  if (record.purchase_jour_kwh !== undefined || record.client_ref) return "steg_meter_reading";
  return "pdf_report";
}

function inferEnergyType(record: ApiRecord): EnergyDocument["energy_type"] {
  const et = record.energy_type ?? "electricity";
  if (et === "natural_gas") return "gas";
  return et;
}

function toFields(record: ApiRecord): ExtractedField[] {
  if (Array.isArray(record.fields)) {
    return record.fields as ExtractedField[];
  }
  const skip = new Set([
    "document_id",
    "document_type",
    "source_file",
    "extraction_method",
    "extraction_confidence",
  ]);
  return Object.entries(record)
    .filter(([key, value]) => !skip.has(key) && value !== null)
    .filter(([, value]) => typeof value !== "object")
    .map(([key, value]) => ({
      key,
      label: key.replace(/_/g, " "),
      value: value as string | number,
    }));
}

export function recordToEnergyDocument(record: ApiRecord): EnergyDocument {
  const docType = inferDocType(record);
  const name = `${getDocumentTypeLabel(docType)} — ${record.date ?? "unknown"}`;
  const extractionMethod = (record.extraction_method ?? "ollama_vision") as ExtractionMethod;

  return {
    id: record.document_id ?? `doc_${Math.random().toString(36).slice(2, 10)}`,
    name,
    doc_type: docType,
    date: record.date ?? "unknown",
    zone: record.zone ?? "global",
    energy_type: inferEnergyType(record),
    quantity_kwh: record.quantity_kwh ?? record.active_energy_kwh ?? record.net_consumption_kwh ?? null,
    unit_raw: record.unit_raw ?? "kWh",
    quantity_raw: record.quantity_raw ?? record.active_energy_kwh ?? record.net_consumption_kwh ?? null,
    amount_tnd: record.amount_tnd ?? null,
    supplier: record.supplier ?? "STEG",
    facture_number: record.facture_number,
    extraction_confidence: record.extraction_confidence ?? 0.8,
    extraction_method: extractionMethod,
    fields: toFields(record),
    anomalies: [],
    co2_kg: null,
    co2_scope: null,
    source_file: record.source_file ?? "upload",
    added_at: new Date().toISOString(),
    content: record.text,
  };
}
