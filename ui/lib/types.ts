export type EnergyDocumentType =
  | "steg_bill"
  | "steg_meter_reading"
  | "excel_report"
  | "pdf_report"
  | "image_invoice";

export type ZoneType = "alpha" | "beta" | "gamma" | "global";

export type EnergyType =
  | "electricity"
  | "gas"
  | "natural_gas"
  | "steam"
  | "hot_water"
  | "chilled_water"
  | "compressed_air";

export type AnomalyType = "RECONCILIATION" | "SPIKE" | "DROPOUT" | "DRIFT";

export type ExtractionMethod =
  | "claude_vision"
  | "ollama_vision"
  | "ollama_text"
  | "pdfplumber"
  | "pandas_excel"
  | "manual";

export interface ExtractedField {
  key: string;
  label: string;
  value: string | number | null;
  unit?: string;
  confidence?: number;
}

export interface AnomalyFlag {
  type: AnomalyType;
  description: string;
  value_observed: number;
  value_expected: number;
  delta_pct: number;
  confidence_score: number;
}

export interface EnergyDocument {
  id: string;
  name: string;
  doc_type: EnergyDocumentType;
  date: string;
  zone: ZoneType;
  energy_type: EnergyType;
  quantity_kwh: number | null;
  unit_raw: string;
  quantity_raw: number | null;
  amount_tnd: number | null;
  supplier?: string;
  facture_number?: string;
  extraction_confidence: number;
  extraction_method: ExtractionMethod;
  fields: ExtractedField[];
  anomalies: AnomalyFlag[];
  co2_kg: number | null;
  co2_scope: "scope1" | "scope2" | null;
  source_file: string;
  added_at: string;
  content?: string;
}

export type EnergyNodeType =
  | "site"
  | "zone"
  | "equipment"
  | "meter"
  | "document"
  | "anomaly"
  | "supplier"
  | "reading";

export type EnergyEdgeType =
  | "supplies"
  | "part_of"
  | "located_in"
  | "measured_by"
  | "extracted_from"
  | "reconciles_with"
  | "discrepancy"
  | "feeds"
  | "not_connected_to"
  | "shared_with";

export interface EnergyNode {
  id: string;
  type: EnergyNodeType;
  label: string;
  description?: string;
  position: { x: number; y: number };
  metadata?: Record<string, unknown>;
  documentId?: string;
  anomaly?: boolean;
  severity?: "ok" | "warning" | "critical";
}

export interface EnergyEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type: EnergyEdgeType;
  strength?: number;
  metadata?: Record<string, unknown>;
}

export interface EnergyGraph {
  nodes: EnergyNode[];
  edges: EnergyEdge[];
}

export type AnalysisResultType =
  | "reconciliation"
  | "anomaly"
  | "co2_estimate"
  | "kpi"
  | "forecast"
  | "insight";

export interface AnalysisResult {
  id: string;
  type: AnalysisResultType;
  title: string;
  content: string;
  severity?: "ok" | "warning" | "critical";
  date?: string;
  value?: number;
  unit?: string;
  document_ids?: string[];
  created_at: string;
}

export interface EnergyKPI {
  label: string;
  value: number | string;
  unit?: string;
  status: "ok" | "warning" | "critical";
  description: string;
}

export interface WorkspaceState {
  documents: EnergyDocument[];
  graph: EnergyGraph;
  analysis: AnalysisResult[];
  kpis: EnergyKPI[];
}
