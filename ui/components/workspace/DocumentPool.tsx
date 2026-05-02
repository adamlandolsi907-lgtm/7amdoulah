"use client";

import React, { useState } from "react";
import {
  FileText,
  Zap,
  AlertTriangle,
  CheckCircle2,
  Filter,
  ChevronRight,
  Upload,
  Receipt,
  TableProperties,
  FileImage,
  FileScan,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EnergyDocument } from "@/lib/types";
import {
  cn,
  formatKwh,
  formatTnd,
  formatMonthYear,
  getDocumentTypeLabel,
  confidenceColor,
} from "@/lib/utils";

const DOC_ICONS: Record<string, React.ReactNode> = {
  steg_bill: <Receipt className="h-5 w-5 text-red-400" />,
  steg_meter_reading: <Zap className="h-5 w-5 text-purple-400" />,
  excel_report: <TableProperties className="h-5 w-5 text-emerald-400" />,
  pdf_report: <FileScan className="h-5 w-5 text-blue-400" />,
  image_invoice: <FileImage className="h-5 w-5 text-amber-400" />,
};

const DOC_COLORS: Record<string, string> = {
  steg_bill: "border-red-900/40 hover:border-red-700/60 bg-red-950/10",
  steg_meter_reading: "border-purple-900/40 hover:border-purple-700/60 bg-purple-950/10",
  excel_report: "border-emerald-900/40 hover:border-emerald-700/60 bg-emerald-950/10",
  pdf_report: "border-blue-900/40 hover:border-blue-700/60 bg-blue-950/10",
  image_invoice: "border-amber-900/40 hover:border-amber-700/60 bg-amber-950/10",
};

interface DocumentPoolProps {
  documents: EnergyDocument[];
  onOpenDocument: (doc: EnergyDocument) => void;
}

function DocCard({ doc, onOpen }: { doc: EnergyDocument; onOpen: () => void }) {
  const hasAnomalies = doc.anomalies.length > 0;

  return (
    <button
      className={cn(
        "group w-full rounded-xl border p-4 text-left transition-all duration-200 hover:shadow-lg hover:shadow-black/30",
        DOC_COLORS[doc.doc_type],
        hasAnomalies && "ring-1 ring-red-800/50"
      )}
      onClick={onOpen}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="shrink-0 rounded-lg border border-gray-800 bg-gray-900 p-2">
            {DOC_ICONS[doc.doc_type]}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-green-100">{doc.name}</p>
            <p className="text-xs text-gray-400">{formatMonthYear(doc.date)}</p>
          </div>
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          {hasAnomalies ? (
            <Badge variant="critical" className="flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {doc.anomalies.length} anomalie{doc.anomalies.length > 1 ? "s" : ""}
            </Badge>
          ) : (
            <Badge variant="success" className="flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" />
              OK
            </Badge>
          )}
          <span className={cn("text-xs font-mono", confidenceColor(doc.extraction_confidence))}>
            {(doc.extraction_confidence * 100).toFixed(0)}% confiance
          </span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-3 border-t border-gray-800/60 pt-3">
        {doc.quantity_kwh !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <Zap className="h-3 w-3 text-amber-400" />
            <span className="font-mono text-green-200">{formatKwh(doc.quantity_kwh)}</span>
          </div>
        )}
        {doc.amount_tnd !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-gray-500">TND</span>
            <span className="font-mono text-blue-200">{formatTnd(doc.amount_tnd)}</span>
          </div>
        )}
        {doc.co2_kg !== null && (
          <div className="flex items-center gap-1.5 text-xs">
            <span className="text-gray-500">CO₂</span>
            <span className="font-mono text-green-300">{(doc.co2_kg / 1000).toFixed(2)} t</span>
          </div>
        )}
        <div className="ml-auto flex items-center gap-1 text-xs text-gray-600 group-hover:text-green-500 transition-colors">
          Ouvrir
          <ChevronRight className="h-3 w-3" />
        </div>
      </div>
    </button>
  );
}

function StatsBar({ documents }: { documents: EnergyDocument[] }) {
  const totalKwh = documents.reduce((s, d) => s + (d.quantity_kwh ?? 0), 0);
  const totalTnd = documents.reduce((s, d) => s + (d.amount_tnd ?? 0), 0);
  const anomalyCount = documents.filter((d) => d.anomalies.length > 0).length;
  const avgConf = documents.length
    ? documents.reduce((s, d) => s + d.extraction_confidence, 0) / documents.length
    : 0;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {[
        { label: "Énergie totale", value: formatKwh(totalKwh), color: "text-amber-300" },
        { label: "Montant total", value: formatTnd(totalTnd), color: "text-blue-300" },
        { label: "Anomalies", value: `${anomalyCount} doc${anomalyCount !== 1 ? "s" : ""}`, color: anomalyCount > 0 ? "text-red-300" : "text-green-300" },
        { label: "Confiance moy.", value: `${(avgConf * 100).toFixed(1)}%`, color: confidenceColor(avgConf) },
      ].map((stat) => (
        <div key={stat.label} className="rounded-xl border border-gray-800 bg-gray-900/60 p-3">
          <p className="text-xs text-gray-400">{stat.label}</p>
          <p className={cn("mt-1 text-lg font-bold font-mono", stat.color)}>{stat.value}</p>
        </div>
      ))}
    </div>
  );
}

export function DocumentPool({ documents, onOpenDocument }: DocumentPoolProps) {
  const [filterType, setFilterType] = useState("all");
  const [filterAnomaly, setFilterAnomaly] = useState(false);

  const filtered = documents.filter((d) => {
    if (filterType !== "all" && d.doc_type !== filterType) return false;
    if (filterAnomaly && d.anomalies.length === 0) return false;
    return true;
  });

  const anomalyDocs = documents.filter((d) => d.anomalies.length > 0);

  return (
    <div className="flex h-full flex-col gap-0">
      {/* Top bar */}
      <div className="border-b border-gray-800 bg-gray-900/80 px-6 py-4 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-green-100">Pool de Documents</h2>
            <p className="text-xs text-gray-400">
              {documents.length} documents extraits — ADWYA Sidi Daoud
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-gray-500" />
            <Select
              className="w-44 text-xs"
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
            >
              <option value="all">Tous les types</option>
              <option value="steg_bill">Factures STEG</option>
              <option value="steg_meter_reading">Relevés Compteur</option>
              <option value="excel_report">Rapports Excel</option>
              <option value="pdf_report">Rapports PDF</option>
              <option value="image_invoice">Factures Photo</option>
            </Select>
            <Button
              variant={filterAnomaly ? "destructive" : "outline"}
              size="sm"
              onClick={() => setFilterAnomaly(!filterAnomaly)}
              className="text-xs"
            >
              <AlertTriangle className="mr-1.5 h-3.5 w-3.5" />
              Anomalies ({anomalyDocs.length})
            </Button>
            <Button variant="outline" size="sm" className="text-xs opacity-50 cursor-not-allowed" disabled>
              <Upload className="mr-1.5 h-3.5 w-3.5" />
              Importer
            </Button>
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Document list */}
        <ScrollArea className="flex-1">
          <div className="space-y-4 p-6">
            <StatsBar documents={documents} />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {filtered.length === 0 ? (
                <div className="col-span-full py-16 text-center text-gray-500">
                  <FileText className="mx-auto mb-3 h-10 w-10 opacity-30" />
                  <p>Aucun document correspondant aux filtres</p>
                </div>
              ) : (
                filtered.map((doc) => (
                  <DocCard key={doc.id} doc={doc} onOpen={() => onOpenDocument(doc)} />
                ))
              )}
            </div>
          </div>
        </ScrollArea>

        {/* Anomaly sidebar */}
        {anomalyDocs.length > 0 && (
          <div className="hidden w-72 shrink-0 border-l border-gray-800 bg-gray-900/40 xl:block">
            <div className="border-b border-gray-800 px-4 py-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-red-300">
                <AlertTriangle className="h-4 w-4" />
                Alertes de Réconciliation
              </h3>
            </div>
            <ScrollArea className="h-[calc(100%-49px)]">
              <div className="space-y-2 p-4">
                {anomalyDocs.map((doc) =>
                  doc.anomalies.map((anom, i) => (
                    <button
                      key={`${doc.id}-${i}`}
                      className="w-full rounded-lg border border-red-900/40 bg-red-950/20 p-3 text-left hover:border-red-700/60 transition-colors"
                      onClick={() => onOpenDocument(doc)}
                    >
                      <div className="flex items-center gap-2 text-xs font-bold uppercase text-red-400">
                        <AlertTriangle className="h-3 w-3" />
                        {anom.type}
                      </div>
                      <p className="mt-1 text-xs text-gray-300 line-clamp-2">{anom.description}</p>
                      <div className="mt-1.5 flex items-center justify-between text-xs text-gray-500">
                        <span>{formatMonthYear(doc.date)}</span>
                        <span className="font-mono text-red-300">+{anom.delta_pct.toFixed(1)}%</span>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </ScrollArea>
          </div>
        )}
      </div>
    </div>
  );
}
