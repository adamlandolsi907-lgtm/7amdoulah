"use client";

import React from "react";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Zap,
  Leaf,
  FileText,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EnergyDocument } from "@/lib/types";
import {
  cn,
  formatKwh,
  formatTnd,
  formatMonthYear,
  getDocumentTypeLabel,
  confidenceColor,
  getAnomalyColor,
} from "@/lib/utils";

const DOC_TYPE_COLORS: Record<string, string> = {
  steg_bill: "bg-red-900/40 text-red-300 border-red-800",
  steg_meter_reading: "bg-purple-900/40 text-purple-300 border-purple-800",
  excel_report: "bg-emerald-900/40 text-emerald-300 border-emerald-800",
  pdf_report: "bg-blue-900/40 text-blue-300 border-blue-800",
  image_invoice: "bg-amber-900/40 text-amber-300 border-amber-800",
};

const ANOMALY_ICONS: Record<string, React.ReactNode> = {
  RECONCILIATION: <AlertTriangle className="h-4 w-4 text-red-400" />,
  SPIKE: <TrendingUp className="h-4 w-4 text-amber-400" />,
  DROPOUT: <XCircle className="h-4 w-4 text-orange-400" />,
  DRIFT: <TrendingDown className="h-4 w-4 text-yellow-400" />,
};

function ConfidenceDot({ score }: { score: number }) {
  const color = score >= 0.9 ? "bg-green-400" : score >= 0.7 ? "bg-amber-400" : "bg-red-400";
  return (
    <span className={cn("inline-block h-2 w-2 rounded-full", color)} />
  );
}

interface InsightPanelProps {
  document: EnergyDocument;
  relatedDocuments?: EnergyDocument[];
}

export function InsightPanel({ document: doc, relatedDocuments = [] }: InsightPanelProps) {
  const powerFactor = React.useMemo(() => {
    const kwh = doc.fields.find((f) => f.key === "active_energy_kwh")?.value as number | null;
    const kvarh = doc.fields.find((f) => f.key === "reactive_energy_kvarh")?.value as number | null;
    if (kwh && kvarh) {
      return (kwh / Math.sqrt(kwh ** 2 + kvarh ** 2)).toFixed(3);
    }
    return null;
  }, [doc.fields]);

  const hasAnomalies = doc.anomalies.length > 0;

  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-4">

        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("rounded border px-2 py-0.5 text-xs font-semibold", DOC_TYPE_COLORS[doc.doc_type])}>
                {getDocumentTypeLabel(doc.doc_type)}
              </span>
              {doc.date && (
                <span className="text-xs text-gray-400">{formatMonthYear(doc.date)}</span>
              )}
            </div>
            <p className="mt-1 truncate text-xs text-gray-500">{doc.source_file}</p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <ConfidenceDot score={doc.extraction_confidence} />
            <span className={cn("text-xs font-mono font-medium", confidenceColor(doc.extraction_confidence))}>
              {(doc.extraction_confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        {/* Summary KPIs */}
        <div className="grid grid-cols-2 gap-2">
          {doc.quantity_kwh !== null && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <Zap className="h-3 w-3 text-amber-400" />
                Énergie
              </div>
              <p className="mt-1 text-base font-bold text-green-300">
                {formatKwh(doc.quantity_kwh)}
              </p>
            </div>
          )}
          {doc.amount_tnd !== null && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <FileText className="h-3 w-3 text-blue-400" />
                Montant
              </div>
              <p className="mt-1 text-base font-bold text-blue-300">
                {formatTnd(doc.amount_tnd)}
              </p>
            </div>
          )}
          {doc.co2_kg !== null && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <Leaf className="h-3 w-3 text-green-400" />
                CO₂ ({doc.co2_scope ?? "—"})
              </div>
              <p className="mt-1 text-base font-bold text-green-300">
                {(doc.co2_kg / 1000).toFixed(2)} tCO₂
              </p>
            </div>
          )}
          {powerFactor && (
            <div className="rounded-lg border border-gray-800 bg-gray-900 p-3">
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <Zap className="h-3 w-3 text-purple-400" />
                Facteur de Puissance
              </div>
              <p className={cn("mt-1 text-base font-bold", Number(powerFactor) >= 0.9 ? "text-green-300" : "text-red-300")}>
                {powerFactor}
                {Number(powerFactor) < 0.9 && (
                  <span className="ml-1 text-xs text-red-400">⚠ pénalité STEG</span>
                )}
              </p>
            </div>
          )}
        </div>

        {/* Anomalies */}
        {hasAnomalies && (
          <div className="space-y-2">
            <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-red-400">
              <AlertTriangle className="h-3.5 w-3.5" />
              Anomalies détectées
            </h3>
            {doc.anomalies.map((anom, i) => (
              <div key={i} className="rounded-lg border border-red-900/50 bg-red-950/30 p-3">
                <div className="flex items-center gap-2">
                  {ANOMALY_ICONS[anom.type]}
                  <span className={cn("text-xs font-bold uppercase", getAnomalyColor(anom.type))}>
                    {anom.type}
                  </span>
                  <Badge variant="critical" className="ml-auto">
                    {anom.delta_pct > 0 ? "+" : ""}{anom.delta_pct.toFixed(1)}%
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-gray-300">{anom.description}</p>
                <div className="mt-2 grid grid-cols-2 gap-1 text-xs text-gray-500">
                  <span>Observé: <span className="text-red-300">{formatKwh(anom.value_observed)}</span></span>
                  <span>Attendu: <span className="text-green-300">{formatKwh(anom.value_expected)}</span></span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* No anomalies */}
        {!hasAnomalies && (
          <div className="flex items-center gap-2 rounded-lg border border-green-900/40 bg-green-950/20 px-3 py-2">
            <CheckCircle2 className="h-4 w-4 text-green-400" />
            <span className="text-xs text-green-300">Aucune anomalie détectée</span>
          </div>
        )}

        {/* Extracted Fields */}
        <div className="space-y-2">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
            Champs extraits
          </h3>
          <div className="rounded-lg border border-gray-800 overflow-hidden">
            <table className="w-full text-xs">
              <tbody>
                {doc.fields.map((field, i) => (
                  <tr key={field.key} className={cn("border-b border-gray-800 last:border-0", i % 2 === 0 ? "bg-gray-900/60" : "bg-gray-950/60")}>
                    <td className="px-3 py-2 text-gray-400">{field.label}</td>
                    <td className="px-3 py-2 text-right font-mono text-green-200">
                      {field.value === null ? (
                        <span className="text-gray-600">—</span>
                      ) : (
                        <>
                          {typeof field.value === "number"
                            ? field.value.toLocaleString("fr-FR")
                            : field.value}
                          {field.unit && <span className="ml-1 text-gray-500">{field.unit}</span>}
                        </>
                      )}
                    </td>
                    {field.confidence !== undefined && (
                      <td className="px-2 py-2 w-6">
                        <ConfidenceDot score={field.confidence} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Extraction metadata */}
        <div className="flex flex-wrap gap-2 text-xs text-gray-500">
          <span className="rounded border border-gray-800 px-2 py-0.5">
            Méthode: <span className="text-gray-300">{doc.extraction_method}</span>
          </span>
          <span className="rounded border border-gray-800 px-2 py-0.5">
            Zone: <span className="text-gray-300 uppercase">{doc.zone}</span>
          </span>
          <span className="rounded border border-gray-800 px-2 py-0.5">
            Énergie: <span className="text-gray-300">{doc.energy_type}</span>
          </span>
        </div>

        {/* Related documents */}
        {relatedDocuments.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
              Documents liés
            </h3>
            <div className="space-y-1">
              {relatedDocuments.map((rel) => (
                <div key={rel.id} className="flex items-center justify-between rounded border border-gray-800 bg-gray-900/50 px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-green-200">{rel.name}</p>
                    <p className="text-xs text-gray-500">{formatMonthYear(rel.date)}</p>
                  </div>
                  {rel.anomalies.length > 0 && (
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
