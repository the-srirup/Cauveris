"use client";

import React, { useState, useMemo } from "react";
import { SignalTag } from "../primitives/SignalTag";
import { GitBranch, List, Eye, Shield, AlertTriangle, ArrowRight, Check, Database, Wrench } from "lucide-react";

export interface ConstellationNode {
  id: string;
  label: string;
  type: "artifact" | "observation" | "component" | "mechanism" | "hypothesis" | "intervention" | "patch" | "verification";
  provenance: "OBSERVED" | "DECLARED" | "DERIVED" | "CALIBRATED" | "INFERRED" | "SIMULATED" | "VERIFIED" | "WARNING" | "FAILURE";
  confidence: number; // 0 - 1
  hasContradiction?: boolean;
  relevance: number; // 1 - 5
  x: number;
  y: number;
  metadata?: Record<string, any>;
}

export interface ConstellationEdge {
  id: string;
  source: string;
  target: string;
  relationship: "derived_from" | "triggers" | "explains" | "remedies" | "verifies" | "contradicts";
  confidence?: number;
}

export interface CausalConstellationProps extends React.HTMLAttributes<HTMLDivElement> {
  nodes: ConstellationNode[];
  edges: ConstellationEdge[];
  selectedNodeId?: string | null;
  onSelectNode?: (node: ConstellationNode) => void;
  height?: number;
}

export function CausalConstellationView({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  height = 540,
  className = "",
  ...props
}: CausalConstellationProps) {
  const [viewMode, setViewMode] = useState<"graph" | "list">("graph");
  const [filterProvenance, setFilterProvenance] = useState<string>("ALL");
  const [isolateChain, setIsolateChain] = useState<boolean>(false);

  // Filtered nodes based on provenance
  const filteredNodes = useMemo(() => {
    if (filterProvenance === "ALL") return nodes;
    return nodes.filter((n) => n.provenance === filterProvenance);
  }, [nodes, filterProvenance]);

  // Isolate chain calculation (selected node and its ancestors/descendants)
  const activeChainNodeIds = useMemo(() => {
    if (!isolateChain || !selectedNodeId) return null;
    const ids = new Set<string>([selectedNodeId]);
    edges.forEach((e) => {
      if (e.source === selectedNodeId || e.target === selectedNodeId) {
        ids.add(e.source);
        ids.add(e.target);
      }
    });
    return ids;
  }, [isolateChain, selectedNodeId, edges]);

  // Monotone fill & border map for node provenance
  const getNodeShades = (prov: string, isSelected: boolean) => {
    if (isSelected) {
      return { fill: "#27272a", stroke: "#fafafa" };
    }
    switch (prov) {
      case "OBSERVED":
      case "VERIFIED":
        return { fill: "#18181b", stroke: "#d4d4d8" };
      case "DECLARED":
      case "DERIVED":
      case "INFERRED":
        return { fill: "#18181b", stroke: "#a1a1aa" };
      case "FAILURE":
      case "WARNING":
        return { fill: "#18181b", stroke: "#71717a" };
      default:
        return { fill: "#121215", stroke: "#52525b" };
    }
  };

  return (
    <div
      className={`flex flex-col border border-[var(--divider,#27272a)] bg-[var(--panel,#18181b)] rounded-[2px] font-mono select-none ${className}`}
      data-causal-constellation
      {...props}
    >
      {/* Top Controls Toolbar */}
      <div className="flex items-center justify-between border-b border-[var(--divider,#27272a)] bg-[var(--workspace,#121215)] px-4 py-2">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-[var(--text-primary,#f4f4f5)]">
            <GitBranch className="w-4 h-4 text-zinc-300" />
            <span>Causal Constellation</span>
          </div>

          <div className="hidden sm:flex items-center gap-1 pl-3 border-l border-[var(--divider,#27272a)] text-[11px] text-[var(--text-tertiary,#71717a)]">
            <span>Filter:</span>
            {["ALL", "OBSERVED", "INFERRED", "SIMULATED", "VERIFIED"].map((p) => (
              <button
                key={p}
                onClick={() => setFilterProvenance(p)}
                className={`px-1.5 py-0.5 rounded-[2px] transition-colors ${
                  filterProvenance === p
                    ? "bg-[var(--panel-raised,#27272a)] text-white font-bold"
                    : "hover:text-[var(--text-primary,#f4f4f5)]"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        {/* View Mode Toggle & Chain Isolation */}
        <div className="flex items-center gap-2">
          {selectedNodeId && (
            <button
              onClick={() => setIsolateChain(!isolateChain)}
              className={`px-2 py-0.5 text-[11px] border rounded-[2px] transition-colors ${
                isolateChain
                  ? "border-zinc-500 bg-zinc-800 text-white font-bold"
                  : "border-[var(--divider,#27272a)] text-[var(--text-tertiary,#71717a)] hover:text-[var(--text-primary,#f4f4f5)]"
              }`}
            >
              {isolateChain ? "Chain Isolated" : "Isolate Chain"}
            </button>
          )}

          <div className="flex items-center border border-[var(--divider,#27272a)] rounded-[2px] bg-[var(--panel-recessed,#0e0e11)] text-[11px]">
            <button
              onClick={() => setViewMode("graph")}
              className={`flex items-center gap-1 px-2 py-0.5 transition-colors ${
                viewMode === "graph"
                  ? "bg-[var(--workspace,#121215)] text-white font-bold"
                  : "text-[var(--text-tertiary,#71717a)] hover:text-[var(--text-primary,#f4f4f5)]"
              }`}
              title="Interactive 2D Constellation Canvas"
            >
              <Eye className="w-3.5 h-3.5" />
              Graph
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`flex items-center gap-1 px-2 py-0.5 transition-colors ${
                viewMode === "list"
                  ? "bg-[var(--workspace,#121215)] text-white font-bold"
                  : "text-[var(--text-tertiary,#71717a)] hover:text-[var(--text-primary,#f4f4f5)]"
              }`}
              title="Accessible Ledger List"
            >
              <List className="w-3.5 h-3.5" />
              Ledger
            </button>
          </div>
        </div>
      </div>

      {/* Main Canvas / List */}
      {viewMode === "graph" ? (
        <div className="relative w-full overflow-hidden bg-[var(--canvas,#09090b)]" style={{ height }}>
          {filteredNodes.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-xs text-[var(--text-tertiary,#71717a)] font-mono">
              <span>No constellation nodes loaded for current filter.</span>
            </div>
          ) : (
            <svg className="w-full h-full cursor-crosshair" viewBox="0 0 800 500">
              <defs>
                <marker
                  id="arrow"
                  viewBox="0 0 10 10"
                  refX="18"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#52525b" />
                </marker>
                <marker
                  id="arrow-active"
                  viewBox="0 0 10 10"
                  refX="18"
                  refY="5"
                  markerWidth="6"
                  markerHeight="6"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill="#fafafa" />
                </marker>
              </defs>

              {/* Edges */}
              {edges.map((edge) => {
                const srcNode = nodes.find((n) => n.id === edge.source);
                const tgtNode = nodes.find((n) => n.id === edge.target);
                if (!srcNode || !tgtNode) return null;

                const isEdgeInChain =
                  activeChainNodeIds
                    ? activeChainNodeIds.has(edge.source) && activeChainNodeIds.has(edge.target)
                    : true;

                const isSelected =
                  srcNode.id === selectedNodeId || tgtNode.id === selectedNodeId;

                const isContradiction = edge.relationship === "contradicts";

                return (
                  <line
                    key={edge.id}
                    x1={srcNode.x}
                    y1={srcNode.y}
                    x2={tgtNode.x}
                    y2={tgtNode.y}
                    stroke={
                      isSelected
                        ? "#fafafa"
                        : isContradiction
                        ? "#a1a1aa"
                        : "#3f3f46"
                    }
                    strokeWidth={isSelected ? 2 : 1}
                    strokeDasharray={isContradiction ? "4 4" : undefined}
                    opacity={isEdgeInChain ? (isSelected ? 1 : 0.65) : 0.2}
                    markerEnd={isSelected ? "url(#arrow-active)" : "url(#arrow)"}
                    className="transition-all duration-200"
                  />
                );
              })}

              {/* Nodes */}
              {filteredNodes.map((node) => {
                const isSelected = node.id === selectedNodeId;
                const isDimmed = activeChainNodeIds ? !activeChainNodeIds.has(node.id) : false;
                const { fill, stroke } = getNodeShades(node.provenance, isSelected);
                const nodeRadius = 8 + node.relevance * 2;

                return (
                  <g
                    key={node.id}
                    transform={`translate(${node.x}, ${node.y})`}
                    onClick={() => onSelectNode?.(node)}
                    className="cursor-pointer transition-transform duration-150 hover:scale-105"
                    opacity={isDimmed ? 0.25 : 1}
                  >
                    {/* Contradiction / Uncertainty Halo */}
                    {node.hasContradiction && (
                      <circle
                        r={nodeRadius + 6}
                        fill="none"
                        stroke="#a1a1aa"
                        strokeWidth={1.5}
                        strokeDasharray="3 3"
                        className="animate-pulse"
                      />
                    )}

                    {/* Active Selection Ring */}
                    {isSelected && (
                      <circle
                        r={nodeRadius + 5}
                        fill="none"
                        stroke="#fafafa"
                        strokeWidth={2}
                      />
                    )}

                    {/* Node Shape based on Type */}
                    {node.type === "hypothesis" ? (
                      // Diamond for hypothesis
                      <polygon
                        points={`0,-${nodeRadius} ${nodeRadius},0 0,${nodeRadius} -${nodeRadius},0`}
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={1.5}
                      />
                    ) : node.type === "patch" ? (
                      // Square for patch
                      <rect
                        x={-nodeRadius}
                        y={-nodeRadius}
                        width={nodeRadius * 2}
                        height={nodeRadius * 2}
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={1.5}
                      />
                    ) : (
                      // Circle for observation / artifact
                      <circle
                        r={nodeRadius}
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={1.5}
                      />
                    )}

                    {/* Label */}
                    <text
                      y={nodeRadius + 13}
                      textAnchor="middle"
                      fill={isSelected ? "#ffffff" : "#a1a1aa"}
                      fontSize={10}
                      fontFamily="monospace"
                      className="select-none pointer-events-none font-semibold"
                    >
                      {node.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          )}

          {/* Floating Context Legend */}
          <div className="absolute bottom-3 left-3 flex items-center gap-3 bg-[var(--panel,#18181b)]/95 p-2 border border-[var(--divider,#27272a)] text-[10px] text-[var(--text-tertiary,#71717a)] rounded-[2px]">
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-zinc-300 inline-block" /> Observed
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-zinc-500 inline-block" /> Inferred
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-zinc-400 inline-block" /> Simulated
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-zinc-200 inline-block" /> Verified
            </span>
            <span className="flex items-center gap-1.5 text-zinc-300">
              <AlertTriangle className="w-3 h-3 text-zinc-400" /> Contradiction
            </span>
          </div>
        </div>
      ) : (
        /* Accessible Ledger Fallback */
        <div className="divide-y divide-[var(--divider,#27272a)] overflow-y-auto max-h-[500px]">
          {filteredNodes.map((n) => (
            <div
              key={n.id}
              onClick={() => onSelectNode?.(n)}
              className={`p-3 flex items-center justify-between text-xs transition-colors cursor-pointer ${
                n.id === selectedNodeId
                  ? "bg-[var(--workspace,#121215)] border-l-2 border-l-zinc-300 text-[var(--text-primary,#f4f4f5)]"
                  : "hover:bg-[var(--panel-raised,#27272a)] text-[var(--text-secondary,#a1a1aa)]"
              }`}
            >
              <div className="flex items-center gap-3">
                <span className="font-bold text-[var(--text-primary,#f4f4f5)]">{n.label}</span>
                <span className="text-[10px] uppercase text-[var(--text-tertiary,#71717a)]">
                  {n.type}
                </span>
                {n.hasContradiction && (
                  <span className="text-[10px] text-zinc-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3 text-zinc-400" /> Contradicted
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="tabular-nums text-[11px] text-[var(--text-tertiary,#71717a)]">
                  {Math.round(n.confidence * 100)}% conf
                </span>
                <SignalTag signal={n.provenance} size="xs" geometry="instrument-box" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
