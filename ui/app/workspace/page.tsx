"use client";

import React from "react";
import {
  Database,
  Network,
  BarChart3,
  ArrowRight,
  Factory,
  AlertTriangle,
  Zap,
  Leaf,
} from "lucide-react";
import { TooltipProvider, Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { FloatingWindow } from "@/components/viewers/FloatingWindow";
import { InsightPanel } from "@/components/viewers/InsightPanel";
import { DocumentPool, EnergyGraphView, AnalysisPanel } from "@/components/workspace";
import { useWorkspaceStore, type WorkspaceMode } from "@/lib/stores";
import { cn } from "@/lib/utils";

const MODES: { key: WorkspaceMode; label: string; shortLabel: string; icon: React.ReactNode }[] = [
  { key: "pool",     label: "Documents",      shortLabel: "Docs",   icon: <Database className="h-4 w-4" /> },
  { key: "graph",    label: "Graphe Énergétique", shortLabel: "Graphe", icon: <Network className="h-4 w-4" /> },
  { key: "analysis", label: "Analyse & KPI",  shortLabel: "KPI",    icon: <BarChart3 className="h-4 w-4" /> },
];

function ModeSelector({ mode, onChange }: { mode: WorkspaceMode; onChange: (m: WorkspaceMode) => void }) {
  return (
    <div className="flex items-center">
      {MODES.map((m, idx) => (
        <React.Fragment key={m.key}>
          <button
            className={cn(
              "flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200",
              mode === m.key
                ? "bg-green-600 text-gray-950 shadow-lg shadow-green-900/40"
                : "bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-green-200"
            )}
            onClick={() => onChange(m.key)}
          >
            {m.icon}
            <span className="hidden lg:inline">{m.label}</span>
            <span className="inline lg:hidden">{m.shortLabel}</span>
          </button>
          {idx < MODES.length - 1 && (
            <ArrowRight className="mx-2 h-4 w-4 text-gray-700" />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

function HeaderStats({ anomalyCount, docCount }: { anomalyCount: number; docCount: number }) {
  return (
    <div className="hidden items-center gap-3 md:flex">
      <div className="flex items-center gap-1.5 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-1.5">
        <Database className="h-3.5 w-3.5 text-green-400" />
        <span className="text-xs text-gray-300">{docCount} docs</span>
      </div>
      {anomalyCount > 0 && (
        <div className="flex items-center gap-1.5 rounded-lg border border-red-900/50 bg-red-950/20 px-3 py-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
          <span className="text-xs text-red-300">{anomalyCount} anomalie{anomalyCount !== 1 ? "s" : ""}</span>
        </div>
      )}
      <div className="flex items-center gap-1.5 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-1.5">
        <Leaf className="h-3.5 w-3.5 text-green-400" />
        <span className="text-xs text-gray-300">CO₂ actif</span>
      </div>
    </div>
  );
}

export default function WorkspacePage() {
  const {
    mode, setMode,
    documents, graph, analysis, kpis,
    activeViewers,
    openViewer, closeViewer, minimizeViewer, restoreViewer,
    updateViewerPosition, updateViewerSize,
  } = useWorkspaceStore();

  const anomalyCount = documents.filter((d) => d.anomalies.length > 0).length;

  return (
    <TooltipProvider>
      <div className="flex h-screen flex-col bg-gray-950 overflow-hidden">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <header className="flex shrink-0 items-center justify-between gap-4 border-b border-gray-800 bg-gray-900 px-6 py-3">
          {/* Left: brand */}
          <div className="flex items-center gap-3 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-green-600 shadow-lg shadow-green-900/40">
              <Factory className="h-4 w-4 text-gray-950" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-bold text-green-100">ADWYA Energy Intelligence</h1>
              <p className="truncate text-xs text-gray-500">Sidi Daoud · KRAM · REF 226570</p>
            </div>
            <Badge variant="outline" className="hidden sm:block text-green-600 border-green-800">
              Phase 2
            </Badge>
          </div>

          {/* Center: mode switcher */}
          <ModeSelector mode={mode} onChange={setMode} />

          {/* Right: stats + actions */}
          <div className="flex items-center gap-2">
            <HeaderStats anomalyCount={anomalyCount} docCount={documents.length} />
            <Button
              variant="outline"
              size="sm"
              className="text-xs opacity-50 cursor-not-allowed hidden sm:flex"
              disabled
            >
              <Zap className="mr-1.5 h-3.5 w-3.5" />
              Connecter API
            </Button>
          </div>
        </header>

        {/* ── Main content ────────────────────────────────────────────── */}
        <main className="relative flex-1 overflow-hidden">

          {/* Document Pool mode */}
          {mode === "pool" && (
            <DocumentPool
              documents={documents}
              onOpenDocument={openViewer}
            />
          )}

          {/* Knowledge graph mode */}
          {mode === "graph" && (
            <EnergyGraphView
              graph={graph}
              onNodeClick={(node) => {
                if (node.documentId) {
                  const doc = documents.find((d) => d.id === node.documentId);
                  if (doc) openViewer(doc);
                }
              }}
            />
          )}

          {/* Analysis mode */}
          {mode === "analysis" && (
            <AnalysisPanel analysis={analysis} kpis={kpis} />
          )}

          {/* ── Floating document viewers ──────────────────────────── */}
          {activeViewers.map((viewer, idx) => {
            const doc = documents.find((d) => d.id === viewer.documentId);
            if (!doc) return null;

            const relatedDocs = documents.filter(
              (d) => d.id !== doc.id && d.date === doc.date
            );

            return (
              <FloatingWindow
                key={viewer.id}
                id={viewer.id}
                title={viewer.title}
                position={viewer.position}
                size={viewer.size}
                minimized={viewer.minimized}
                minimizedIndex={activeViewers.filter((v) => v.minimized).indexOf(viewer)}
                onClose={() => closeViewer(viewer.id)}
                onPositionChange={(pos) => updateViewerPosition(viewer.id, pos)}
                onSizeChange={(size) => updateViewerSize(viewer.id, size)}
                onMinimize={() => minimizeViewer(viewer.id)}
                onRestore={() => restoreViewer(viewer.id)}
              >
                <InsightPanel document={doc} relatedDocuments={relatedDocs} />
              </FloatingWindow>
            );
          })}
        </main>
      </div>
    </TooltipProvider>
  );
}
