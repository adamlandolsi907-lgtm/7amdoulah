"use client";

import { create } from "zustand";
import type { EnergyDocument, EnergyGraph, AnalysisResult, EnergyKPI } from "./types";
import { MOCK_DOCUMENTS, MOCK_GRAPH, MOCK_ANALYSIS, MOCK_KPIS } from "./mock-data";

export type WorkspaceMode = "pool" | "graph" | "analysis";

interface ViewerEntry {
  id: string;
  documentId: string;
  title: string;
  position: { x: number; y: number };
  size: { width: number; height: number };
  minimized: boolean;
}

interface WorkspaceState {
  mode: WorkspaceMode;
  documents: EnergyDocument[];
  graph: EnergyGraph;
  analysis: AnalysisResult[];
  kpis: EnergyKPI[];
  activeViewers: ViewerEntry[];
  selectedNodeId: string | null;
  filterDocType: string;
  filterDate: string;
  filterAnomaly: boolean;

  setMode: (mode: WorkspaceMode) => void;
  setSelectedNode: (id: string | null) => void;
  setFilter: (key: "filterDocType" | "filterDate" | "filterAnomaly", value: string | boolean) => void;

  openViewer: (doc: EnergyDocument) => void;
  closeViewer: (id: string) => void;
  minimizeViewer: (id: string) => void;
  restoreViewer: (id: string) => void;
  updateViewerPosition: (id: string, pos: { x: number; y: number }) => void;
  updateViewerSize: (id: string, size: { width: number; height: number }) => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  mode: "pool",
  documents: MOCK_DOCUMENTS,
  graph: MOCK_GRAPH,
  analysis: MOCK_ANALYSIS,
  kpis: MOCK_KPIS,
  activeViewers: [],
  selectedNodeId: null,
  filterDocType: "all",
  filterDate: "all",
  filterAnomaly: false,

  setMode: (mode) => set({ mode }),
  setSelectedNode: (id) => set({ selectedNodeId: id }),
  setFilter: (key, value) => set({ [key]: value } as Partial<WorkspaceState>),

  openViewer: (doc) => {
    const existing = get().activeViewers.find((v) => v.documentId === doc.id);
    if (existing) {
      set((s) => ({
        activeViewers: s.activeViewers.map((v) =>
          v.documentId === doc.id ? { ...v, minimized: false } : v
        ),
      }));
      return;
    }
    const offset = get().activeViewers.length;
    const entry: ViewerEntry = {
      id: `viewer-${doc.id}`,
      documentId: doc.id,
      title: doc.name,
      position: { x: 80 + offset * 25, y: 80 + offset * 25 },
      size: { width: 680, height: 520 },
      minimized: false,
    };
    set((s) => ({ activeViewers: [...s.activeViewers, entry] }));
  },

  closeViewer: (id) =>
    set((s) => ({ activeViewers: s.activeViewers.filter((v) => v.id !== id) })),

  minimizeViewer: (id) =>
    set((s) => ({
      activeViewers: s.activeViewers.map((v) =>
        v.id === id ? { ...v, minimized: true } : v
      ),
    })),

  restoreViewer: (id) =>
    set((s) => ({
      activeViewers: s.activeViewers.map((v) =>
        v.id === id ? { ...v, minimized: false } : v
      ),
    })),

  updateViewerPosition: (id, pos) =>
    set((s) => ({
      activeViewers: s.activeViewers.map((v) =>
        v.id === id ? { ...v, position: pos } : v
      ),
    })),

  updateViewerSize: (id, size) =>
    set((s) => ({
      activeViewers: s.activeViewers.map((v) =>
        v.id === id ? { ...v, size } : v
      ),
    })),
}));
