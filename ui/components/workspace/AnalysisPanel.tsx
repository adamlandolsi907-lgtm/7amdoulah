"use client";

import React, { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Leaf,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronDown,
  ChevronRight,
  Activity,
  Zap,
  Info,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { AnalysisResult, EnergyKPI } from "@/lib/types";
import { cn } from "@/lib/utils";

const RESULT_ICONS: Record<string, React.ReactNode> = {
  reconciliation: <AlertTriangle className="h-5 w-5 text-red-400" />,
  anomaly:        <Activity className="h-5 w-5 text-amber-400" />,
  co2_estimate:   <Leaf className="h-5 w-5 text-green-400" />,
  kpi:            <BarChart3 className="h-5 w-5 text-blue-400" />,
  forecast:       <TrendingUp className="h-5 w-5 text-purple-400" />,
  insight:        <Info className="h-5 w-5 text-cyan-400" />,
};

const RESULT_COLORS: Record<string, string> = {
  reconciliation: "border-red-900/50 bg-red-950/20",
  anomaly:        "border-amber-900/50 bg-amber-950/20",
  co2_estimate:   "border-green-900/50 bg-green-950/20",
  kpi:            "border-blue-900/50 bg-blue-950/20",
  forecast:       "border-purple-900/50 bg-purple-950/20",
  insight:        "border-cyan-900/50 bg-cyan-950/20",
};

const TYPE_LABELS: Record<string, string> = {
  reconciliation: "Réconciliation",
  anomaly:        "Anomalie",
  co2_estimate:   "Bilan CO₂",
  kpi:            "KPI",
  forecast:       "Prévision",
  insight:        "Insight",
};

const SEVERITY_BADGE: Record<string, React.ReactNode> = {
  ok:       <Badge variant="success">OK</Badge>,
  warning:  <Badge variant="warning">Attention</Badge>,
  critical: <Badge variant="critical">Critique</Badge>,
};

function KPICard({ kpi }: { kpi: EnergyKPI }) {
  const colors = {
    ok:       { value: "text-green-300", border: "border-green-900/40 bg-green-950/10" },
    warning:  { value: "text-amber-300", border: "border-amber-900/40 bg-amber-950/10" },
    critical: { value: "text-red-300",   border: "border-red-900/40 bg-red-950/10" },
  }[kpi.status];

  const Icon = kpi.status === "ok" ? CheckCircle2 : kpi.status === "critical" ? AlertTriangle : Minus;
  const iconColor = kpi.status === "ok" ? "text-green-400" : kpi.status === "critical" ? "text-red-400" : "text-amber-400";

  return (
    <div className={cn("rounded-xl border p-4", colors.border)}>
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs text-gray-400">{kpi.label}</p>
        <Icon className={cn("h-4 w-4 shrink-0", iconColor)} />
      </div>
      <p className={cn("mt-1 text-xl font-bold font-mono", colors.value)}>
        {kpi.value}
        {kpi.unit && <span className="ml-1 text-sm font-normal text-gray-400">{kpi.unit}</span>}
      </p>
      <p className="mt-1 text-xs text-gray-500 line-clamp-2">{kpi.description}</p>
    </div>
  );
}

function AnalysisCard({ result }: { result: AnalysisResult }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={cn("rounded-xl border transition-all", RESULT_COLORS[result.type])}>
      <button
        className="w-full px-4 py-3 text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-start gap-3">
          <div className="shrink-0 mt-0.5">{RESULT_ICONS[result.type]}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Badge variant="secondary" className="text-xs">{TYPE_LABELS[result.type]}</Badge>
                {result.severity && SEVERITY_BADGE[result.severity]}
              </div>
              {expanded ? (
                <ChevronDown className="h-4 w-4 text-gray-500 shrink-0" />
              ) : (
                <ChevronRight className="h-4 w-4 text-gray-500 shrink-0" />
              )}
            </div>
            <p className="mt-1 text-sm font-semibold text-green-100">{result.title}</p>
            {result.value !== undefined && result.value !== null && (
              <p className="text-xs text-gray-400 mt-0.5">
                <span className="font-mono text-green-300">
                  {typeof result.value === "number" ? result.value.toLocaleString("fr-FR") : result.value}
                </span>
                {result.unit && <span className="ml-1">{result.unit}</span>}
              </p>
            )}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="border-t border-gray-800/50 px-4 pb-4 pt-3 animate-fade-in">
          <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{result.content}</p>
          {result.date && (
            <p className="mt-2 text-xs text-gray-500">Période: {result.date}</p>
          )}
        </div>
      )}
    </div>
  );
}

interface AnalysisPanelProps {
  analysis: AnalysisResult[];
  kpis: EnergyKPI[];
}

export function AnalysisPanel({ analysis, kpis }: AnalysisPanelProps) {
  const critical = analysis.filter((a) => a.severity === "critical");
  const warning  = analysis.filter((a) => a.severity === "warning");
  const ok       = analysis.filter((a) => a.severity === "ok" || !a.severity);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b border-gray-800 bg-gray-900/80 px-6 py-4 backdrop-blur">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-green-100">Analyse Énergétique</h2>
            <p className="text-xs text-gray-400">
              {critical.length} critique · {warning.length} attention · {ok.length} normal
            </p>
          </div>
          <div className="flex items-center gap-2">
            {critical.length > 0 && (
              <Badge variant="critical" className="flex items-center gap-1">
                <AlertTriangle className="h-3 w-3" />
                {critical.length} critique{critical.length > 1 ? "s" : ""}
              </Badge>
            )}
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1">
        <div className="space-y-6 p-6">
          {/* KPIs */}
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-gray-300">
              <BarChart3 className="h-4 w-4 text-blue-400" />
              KPI ISO 50001 — Octobre 2025
            </h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {kpis.map((kpi) => (
                <KPICard key={kpi.label} kpi={kpi} />
              ))}
            </div>
          </section>

          {/* Critical findings */}
          {critical.length > 0 && (
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-red-300">
                <AlertTriangle className="h-4 w-4" />
                Anomalies Critiques
              </h3>
              <div className="space-y-3">
                {critical.map((r) => <AnalysisCard key={r.id} result={r} />)}
              </div>
            </section>
          )}

          {/* Warnings */}
          {warning.length > 0 && (
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-amber-300">
                <Activity className="h-4 w-4" />
                Points d'Attention
              </h3>
              <div className="space-y-3">
                {warning.map((r) => <AnalysisCard key={r.id} result={r} />)}
              </div>
            </section>
          )}

          {/* OK / info */}
          {ok.length > 0 && (
            <section>
              <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-green-300">
                <CheckCircle2 className="h-4 w-4" />
                Bilans &amp; Insights
              </h3>
              <div className="space-y-3">
                {ok.map((r) => <AnalysisCard key={r.id} result={r} />)}
              </div>
            </section>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
