"use client";

import React, { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  Handle,
  Position,
  BackgroundVariant,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Building2,
  Layers,
  Cpu,
  Gauge,
  FileText,
  AlertTriangle,
  Truck,
  Activity,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { EnergyGraph as EnergyGraphType, EnergyNode, EnergyEdge } from "@/lib/types";

const NODE_CONFIG: Record<string, { icon: React.ReactNode; bg: string; border: string; text: string }> = {
  site:     { icon: <Building2 className="h-4 w-4" />, bg: "bg-amber-950/80", border: "border-amber-700", text: "text-amber-200" },
  zone:     { icon: <Layers className="h-4 w-4" />,    bg: "bg-blue-950/80",  border: "border-blue-700",  text: "text-blue-200" },
  equipment:{ icon: <Cpu className="h-4 w-4" />,       bg: "bg-green-950/80", border: "border-green-700", text: "text-green-200" },
  meter:    { icon: <Gauge className="h-4 w-4" />,     bg: "bg-purple-950/80",border: "border-purple-700",text: "text-purple-200" },
  document: { icon: <FileText className="h-4 w-4" />,  bg: "bg-red-950/80",   border: "border-red-800",   text: "text-red-200" },
  anomaly:  { icon: <AlertTriangle className="h-4 w-4" />, bg: "bg-red-950",  border: "border-red-500",   text: "text-red-300" },
  supplier: { icon: <Truck className="h-4 w-4" />,     bg: "bg-gray-800",     border: "border-gray-600",  text: "text-gray-200" },
  reading:  { icon: <Activity className="h-4 w-4" />,  bg: "bg-cyan-950/80",  border: "border-cyan-700",  text: "text-cyan-200" },
};

const EDGE_STYLES: Record<string, { stroke: string; strokeDasharray?: string }> = {
  supplies:         { stroke: "#22c55e" },
  part_of:          { stroke: "#3b82f6" },
  located_in:       { stroke: "#6b7280" },
  measured_by:      { stroke: "#a855f7" },
  extracted_from:   { stroke: "#f59e0b" },
  reconciles_with:  { stroke: "#06b6d4" },
  discrepancy:      { stroke: "#ef4444", strokeDasharray: "5 3" },
  feeds:            { stroke: "#10b981" },
  not_connected_to: { stroke: "#dc2626", strokeDasharray: "8 4" },
  shared_with:      { stroke: "#f97316", strokeDasharray: "4 2" },
};

function EnergyNodeComponent({ data }: NodeProps) {
  const node = data as unknown as EnergyNode & {
    config: typeof NODE_CONFIG["site"];
    onExpandDocument?: (documentId: string) => void;
  };
  const cfg = node.config ?? NODE_CONFIG["site"];
  const isAnomaly = node.anomaly;
  const severity = node.severity;

  return (
    <div
      className={cn(
        "group relative min-w-[140px] max-w-[200px] rounded-xl border-2 px-3 py-2.5 shadow-lg transition-all",
        cfg.bg,
        cfg.border,
        isAnomaly && "ring-2 ring-red-500/60 animate-pulse-subtle",
        severity === "critical" && "ring-2 ring-red-500",
        severity === "warning" && "ring-1 ring-amber-500/60",
      )}
    >
      <Handle type="target" position={Position.Top} className="!bg-green-500 !border-0 !w-2 !h-2" />
      <Handle type="source" position={Position.Bottom} className="!bg-green-500 !border-0 !w-2 !h-2" />
      <Handle type="target" position={Position.Left} className="!bg-green-500 !border-0 !w-2 !h-2" />
      <Handle type="source" position={Position.Right} className="!bg-green-500 !border-0 !w-2 !h-2" />

      <div className="flex items-center gap-2">
        <span className={cn("shrink-0", cfg.text)}>{cfg.icon}</span>
        <span className={cn("truncate text-xs font-semibold", cfg.text)}>{node.label}</span>
        {node.type === "document" && node.documentId && node.onExpandDocument && (
          <button
            className="ml-auto inline-flex h-5 w-5 items-center justify-center rounded border border-gray-600 bg-gray-800/80 text-green-300 hover:bg-gray-700"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              node.onExpandDocument?.(node.documentId as string);
            }}
            title="Show 5 semantically similar documents"
          >
            <Plus className="h-3 w-3" />
          </button>
        )}
        {isAnomaly && severity === "critical" && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-red-400" />
        )}
      </div>

      {node.description && (
        <div className="absolute left-0 top-full z-50 mt-2 hidden w-64 rounded-lg border border-gray-700 bg-gray-900 p-3 shadow-2xl group-hover:block">
          <p className="text-xs font-semibold text-green-300 mb-1">{node.label}</p>
          <p className="text-xs text-gray-300 whitespace-pre-wrap">{node.description}</p>
        </div>
      )}
    </div>
  );
}

const nodeTypes = { energy: EnergyNodeComponent };

interface EnergyGraphProps {
  graph: EnergyGraphType;
  onNodeClick?: (node: EnergyNode) => void;
  onExpandDocument?: (documentId: string) => void;
}

export function EnergyGraphView({ graph, onNodeClick, onExpandDocument }: EnergyGraphProps) {
  const rfNodes: Node[] = useMemo(
    () =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: "energy",
        position: n.position,
        data: {
          ...n,
          config: NODE_CONFIG[n.type] ?? NODE_CONFIG["site"],
          onExpandDocument,
        },
      })),
    [graph.nodes, onExpandDocument]
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      graph.edges.map((e) => {
        const style = EDGE_STYLES[e.type] ?? { stroke: "#6b7280" };
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          label: e.label,
          labelStyle: { fill: "#9ca3af", fontSize: 9 },
          labelBgStyle: { fill: "#111827", fillOpacity: 0.8 },
          style: { stroke: style.stroke, strokeWidth: 1.5, strokeDasharray: style.strokeDasharray },
          animated: e.type === "supplies" || e.type === "feeds",
        };
      }),
    [graph.edges]
  );

  const [nodes, , onNodesChange] = useNodesState(rfNodes);
  const [edges, , onEdgesChange] = useEdgesState(rfEdges);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      const original = graph.nodes.find((n) => n.id === node.id);
      if (original && onNodeClick) onNodeClick(original);
    },
    [graph.nodes, onNodeClick]
  );

  const LEGEND = Object.entries(NODE_CONFIG).map(([type, cfg]) => ({
    type,
    ...cfg,
  }));

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        className="bg-gray-950"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#1a2e1a" />
        <Controls className="!bg-gray-900 !border-gray-700 [&>button]:!bg-gray-800 [&>button]:!border-gray-700 [&>button]:!text-green-300" />
        <MiniMap
          className="!bg-gray-900 !border-gray-700"
          nodeColor={(n) => {
            const t = (n.data as unknown as EnergyNode).type;
            const colors: Record<string, string> = {
              site: "#f59e0b", zone: "#3b82f6", equipment: "#22c55e",
              meter: "#a855f7", document: "#ef4444", anomaly: "#dc2626",
              supplier: "#6b7280", reading: "#06b6d4",
            };
            return colors[t] ?? "#6b7280";
          }}
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-16 left-4 rounded-xl border border-gray-800 bg-gray-900/95 p-3 backdrop-blur">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">Légende</p>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {LEGEND.map(({ type, icon, text }) => (
            <div key={type} className="flex items-center gap-1.5">
              <span className={cn("text-xs", text)}>{icon}</span>
              <span className="text-xs text-gray-400 capitalize">{type}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 border-t border-gray-800 pt-2 space-y-1">
          {[
            { color: "#ef4444", dash: "5 3", label: "Discordance" },
            { color: "#dc2626", dash: "8 4", label: "Non connecté" },
            { color: "#f97316", dash: "4 2", label: "Partagé" },
            { color: "#22c55e", dash: undefined, label: "Alimentation" },
          ].map(({ color, dash, label }) => (
            <div key={label} className="flex items-center gap-2">
              <svg width="24" height="8">
                <line x1="0" y1="4" x2="24" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dash} />
              </svg>
              <span className="text-xs text-gray-400">{label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
