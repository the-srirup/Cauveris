"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import {
  Button,
  Badge,
  PageHeader,
  Toolbar,
  ToolbarGroup,
  ToolbarItem,
  ToolbarSeparator,
  Input,
  Select,
  Panel,
  PanelSection,
  PanelStack,
  PanelHeader,
  EmptyState,
  EmptyStateIcons,
  Stat,
  KV,
} from "@/components/ui";
import { ZoomIn, ZoomOut, Maximize, RotateCcw, Sliders } from "lucide-react";
import {
  api,
  Hypothesis,
  TemporalVisualizationResponse,
  TemporalVisualizationCausalChain,
} from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { AuthGate } from "@/components/AuthGate";

export default function CausalConstellation() {
  return (
    <AuthGate redirect="/causal-constellation" loadingLabel="Loading causal constellation...">
      <CausalConstellationContent />
    </AuthGate>
  );
}

interface LaneNode {
  id: string;
  label: string;
  subtitle: string;
  tier: number;
  x: number;
  y: number;
  color: string;
  badgeTone: "primary" | "success" | "warning" | "danger" | "neutral";
  eventCount: number;
  domains: string[];
  sources: string[];
  isSafetyOutcome: boolean;
  start_s: number;
  end_s: number;
}

interface LaneEdge {
  id: string;
  source: string;
  target: string;
  edgeCount: number;
  provenance: string;
  dashed: boolean;
}

const LANE_DISPLAY_NAMES: Record<string, string> = {
  deployment_events: "Deployment",
  system: "Host System",
  cloud_requests: "Cloud Inference",
  gpu_queue: "GPU Queue",
  network: "Network",
  detection_publication: "Detection Publication",
  tf_events: "Transform State",
  controller_latency: "Control Loop",
  safety_state: "Safety Monitor",
};

function laneLabel(lane: string): string {
  return LANE_DISPLAY_NAMES[lane] ?? lane.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const PROVENANCE_LABELS: Record<string, string> = {
  deployment_chain: "Deployment Horizon",
  temporal_proximity: "Temporal Order",
  cross_domain_handoff: "Cross-Domain Handoff",
  ros_topic_order: "ROS Topic Order",
  otel_trace_order: "Trace Order",
  log_node_order: "Log Node Order",
};

function provenanceLabel(prov: string): string {
  return PROVENANCE_LABELS[prov] ?? prov.replace(/_/g, " ");
}

function CausalConstellationContent() {
  const { incidentId } = useActiveIncident();

  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [testResults, setTestResults] = useState<Record<string, any>>({});
  const [selectedNode, setSelectedNode] = useState<string>("");
  const [selectedLaneId, setSelectedLaneId] = useState<string>("");
  const [selectedChainIndex, setSelectedChainIndex] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const [confidenceThreshold, setConfidenceThreshold] = useState(50);
  const [layoutMode, setLayoutMode] = useState<"hierarchical" | "constellation">(
    "hierarchical"
  );
  const [evidenceFilter, setEvidenceFilter] = useState<
    "ALL" | "SUPPORTED" | "CONTRADICTED" | "UNKNOWN"
  >("ALL");
  const [graph, setGraph] = useState<TemporalVisualizationResponse | null>(null);

  const loadData = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const [hypRes, visRes] = await Promise.all([
        api.getHypotheses(id),
        api.getTemporalVisualization(id).catch(() => null),
      ]);

      const hyps = hypRes?.hypotheses ?? [];
      setHypotheses(hyps);
      if (hyps.length > 0) {
        setSelectedNode((prev) => prev || hyps[0].hypothesis_id || hyps[0].id);
      }
      setGraph(visRes);
    } catch (e: any) {
      setError(e.message || "Failed to load causal data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadData(incidentId);
    }
  }, [incidentId]);

  const handleTestHypothesis = async (hyp: Hypothesis) => {
    const hypKey = hyp.hypothesis_id || hyp.id;
    setTestingId(hypKey);
    setError(null);
    try {
      if (!incidentId) {
        throw new Error("No incident selected");
      }

      notify(`Running digital twin experiment branch for ${hyp.title}...`, "info");
      const result = await api.testHypothesis(incidentId, hypKey);

      setTestResults((prev) => ({
        ...prev,
        [hypKey]: result,
      }));

      if (result.status === "CONFIRMED") {
        notify(
          `${hyp.title}: Confirmed as root cause. Intervention eliminated emergency stops (0% failures).`,
          "success"
        );
      } else {
        notify(
          `${hyp.title}: Refuted. Failures persisted at ${Math.round(
            result.reproduction_rate * 100
          )}% under intervention.`,
          "info"
        );
      }
    } catch (e: any) {
      setError(e.message || "Failed to test hypothesis");
      notify(e.message || "Hypothesis testing failed", "error");
    } finally {
      setTestingId(null);
    }
  };

  // Real lane DAG derived from the backend's evidence graph.
  const { laneNodes, laneEdges } = useMemo(() => {
    const rawNodes: LaneNode[] = [];
    const rawEdges: LaneEdge[] = [];
    if (!graph?.lanes?.length) return { laneNodes: rawNodes, laneEdges: rawEdges };

    const safetyLanes = new Set(
      (graph.causal_chains ?? [])
        .filter((c) => c.is_safety_outcome)
        .map((c) => c.terminal_lane)
    );

    const byTier = new Map<number, typeof graph.lanes>();
    graph.lanes.forEach((lane) => {
      const bucket = byTier.get(lane.tier) ?? [];
      bucket.push(lane);
      byTier.set(lane.tier, bucket);
    });
    const tiers = Array.from(byTier.keys()).sort((a, b) => a - b);

    const xByTier = new Map<number, number>();
    tiers.forEach((tier, idx) => {
      xByTier.set(tier, 120 + idx * 200);
    });

    const maxTier = tiers.length > 0 ? tiers[tiers.length - 1] : 0;

    graph.lanes.forEach((lane) => {
      const siblings = byTier.get(lane.tier) ?? [lane];
      const idx = siblings.indexOf(lane);
      const spacing = Math.max(70, 300 / Math.max(siblings.length, 1));
      const y = 120 + idx * spacing + (maxTier - lane.tier) * 8;
      const isSafety = safetyLanes.has(lane.lane);
      const domainLabel = lane.domains.join(" + ");

      rawNodes.push({
        id: lane.lane,
        label: laneLabel(lane.lane),
        subtitle: `${lane.event_count} events · ${domainLabel}`,
        tier: lane.tier,
        x: xByTier.get(lane.tier) ?? 120,
        y,
        color: isSafety
          ? "var(--color-danger-fg)"
          : lane.tier === 0
            ? "var(--color-attention-fg)"
            : "var(--color-accent-fg)",
        badgeTone: isSafety ? "danger" : lane.tier === 0 ? "warning" : "primary",
        eventCount: lane.event_count,
        domains: lane.domains,
        sources: lane.sources,
        isSafetyOutcome: isSafety,
        start_s: lane.start_s,
        end_s: lane.end_s,
      });
    });

    (graph.lane_edges ?? []).forEach((edge) => {
      const provCounts = edge.provenance ?? {};
      // Show the most specific provenance on the edge, not the horizon marker.
      const ranked = Object.entries(provCounts).sort((a, b) => {
        const order = [
          "cross_domain_handoff",
          "log_node_order",
          "ros_topic_order",
          "otel_trace_order",
          "temporal_proximity",
          "deployment_chain",
        ];
        return order.indexOf(a[0]) - order.indexOf(b[0]);
      });
      const topProv = ranked[0]?.[0] ?? "unknown";
      rawEdges.push({
        id: `lane_edge_${edge.source}__${edge.target}`,
        source: edge.source,
        target: edge.target,
        edgeCount: edge.edge_count,
        provenance: topProv,
        dashed: topProv === "deployment_chain",
      });
    });

    return { laneNodes: rawNodes, laneEdges: rawEdges };
  }, [graph]);

  // The chain actually under inspection: the selected safety chain, else the
  // longest chain the backend found.
  const activeChain: TemporalVisualizationCausalChain | null = useMemo(() => {
    const chains = graph?.causal_chains ?? [];
    if (chains.length === 0) return null;
    const safety = chains.filter((c) => c.is_safety_outcome);
    const pool = safety.length > 0 ? safety : chains;
    const idx = Math.min(selectedChainIndex, pool.length - 1);
    return pool[idx] ?? null;
  }, [graph, selectedChainIndex]);

  const safetyChains = (graph?.causal_chains ?? []).filter((c) => c.is_safety_outcome);

  // Evidence state is a property of a *hypothesis* (confirmed / refuted by the
  // sandbox), so it filters the hypothesis cards rather than the lane DAG.
  const visibleHypotheses = useMemo(() => {
    if (evidenceFilter === "ALL") return hypotheses;
    return hypotheses.filter((hyp) => {
      const key = hyp.hypothesis_id || hyp.id;
      const result = testResults[key];
      const state =
        result?.status === "CONFIRMED"
          ? "SUPPORTED"
          : result?.status === "REFUTED"
            ? "CONTRADICTED"
            : "UNKNOWN";
      return state === evidenceFilter;
    });
  }, [hypotheses, evidenceFilter, testResults]);

  const selectedLane = useMemo(
    () => laneNodes.find((n) => n.id === selectedLaneId) ?? null,
    [laneNodes, selectedLaneId]
  );

  const incomingEdges = useMemo(
    () => laneEdges.filter((e) => e.target === selectedLaneId),
    [laneEdges, selectedLaneId]
  );

  const outgoingEdges = useMemo(
    () => laneEdges.filter((e) => e.source === selectedLaneId),
    [laneEdges, selectedLaneId]
  );

  const getStatusConfig = (hyp: Hypothesis) => {
    const hypKey = hyp.hypothesis_id || hyp.id;
    const testResult = testResults[hypKey];

    if (testResult) {
      if (testResult.status === "CONFIRMED") {
        return {
          label: "CONFIRMED ROOT CAUSE",
          tone: "success" as const,
          sub: "0% Failures in Twin",
        };
      }
      return {
        label: "REFUTED",
        tone: "danger" as const,
        sub: `${Math.round(testResult.reproduction_rate * 100)}% Failure Rate`,
      };
    }

    const conf = Math.round(
      (hyp.confidence_prior ?? (hyp.confidence ? hyp.confidence / 100 : 0.5)) * 100
    );
    if (conf >= 85)
      return { label: "PRIMARY CANDIDATE", tone: "primary" as const, sub: `${conf}% Confidence` };
    if (conf >= 50)
      return { label: "PLAUSIBLE", tone: "warning" as const, sub: `${conf}% Confidence` };
    return {
      label: "LOW PROBABILITY",
      tone: "neutral" as const,
      sub: `${conf}% Confidence`,
    };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    dragStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStartRef.current.x,
      y: e.clientY - dragStartRef.current.y,
    });
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const hasGraph = laneNodes.length > 0;
  const summary = graph?.summary;

  return (
    <div className="w-full space-y-6">
      {/* Header */}
      <PageHeader
        title="Causal Constellation"
        subtitle="Causal DAG inference and root-cause hypothesis generation"
        badge={
          <Badge tone="primary" dot={true}>
            {hypotheses.length} Root-Cause Hypotheses Evaluated
          </Badge>
        }
      />

      {error && (
        <div className="p-4 bg-[var(--color-danger-muted)] border border-[var(--color-danger-muted)]/30 rounded-[var(--radius-md)] text-[var(--color-danger-fg)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Real graph summary */}
      {summary && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Stat
            label="Evidence Nodes"
            value={summary.total_events}
            sub="Timeline events with causal fingerprints"
          />
          <Stat
            label="Causal Edges"
            value={summary.causal_edge_count}
            sub={`${Object.keys(summary.provenance_breakdown).length} provenance rules`}
          />
          <Stat
            label="Propagation Chains"
            value={summary.chain_count}
            sub={`${safetyChains.length} terminating in a safety outcome`}
            trend={safetyChains.length > 0 ? "danger" : "muted"}
          />
          <Stat
            label="Temporal Anomalies"
            value={summary.anomaly_count}
            sub={`Confidence ${(summary.confidence * 100).toFixed(0)}%`}
            trend={summary.is_anomalous ? "warning" : "success"}
          />
        </div>
      )}

      {/* Main Grid: Hypotheses on Left, Dynamic SVG Causal Graph on Right */}
      <div className="grid gap-6 lg:grid-cols-[1.1fr_1.9fr]">
        {/* Left: Hypotheses Cards */}
        <div className="space-y-4">
          <Panel padding="none">
            <PanelHeader
              title="Falsifiable Causal Hypotheses"
              subtitle="Ranked by Bayesian prior confidence. Test in sandbox to confirm."
              divider={true}
            />
            <PanelSection dividerBefore={false}>
              {hypotheses.length === 0 ? (
                <EmptyState
                  icon={EmptyStateIcons.search}
                  title="No hypotheses generated"
                  description={
                    loading
                      ? "Running hypothesis generation…"
                      : "The pipeline has not produced root-cause hypotheses for this incident yet. Run the investigation pipeline to generate them."
                  }
                  size="sm"
                />
              ) : visibleHypotheses.length === 0 ? (
                <EmptyState
                  icon={EmptyStateIcons.search}
                  title={`No ${evidenceFilter.toLowerCase()} hypotheses`}
                  description="Change the evidence-state filter or test a hypothesis in the sandbox to populate this state."
                  size="sm"
                />
              ) : (
                <PanelStack space="md">
                  {visibleHypotheses.map((hyp) => {
                    const hypKey = hyp.hypothesis_id || hyp.id;
                    const statusInfo = getStatusConfig(hyp);
                    const isSelected = selectedNode === hypKey;
                    const isTesting = testingId === hypKey;
                    const testResult = testResults[hypKey];

                    return (
                      <Panel
                        key={hypKey}
                        variant="inset"
                        padding="sm"
                        className={`cursor-pointer transition-all border ${
                          isSelected
                            ? "ring-2 ring-[var(--color-accent-fg)] border-[var(--color-accent-fg)] bg-[var(--color-canvas-subtle)]"
                            : "hover:border-[var(--color-border-strong)] bg-[var(--color-canvas)]"
                        }`}
                        onClick={() => setSelectedNode(hypKey)}
                      >
                        <PanelSection dividerBefore={false} className="space-y-3">
                          <div className="flex items-center justify-between">
                            <Badge tone={statusInfo.tone} size="sm">
                              {statusInfo.label}
                            </Badge>
                            <span className="text-xs font-mono font-semibold text-[var(--color-fg-muted)]">
                              {statusInfo.sub}
                            </span>
                          </div>

                          <div>
                            <h3 className="text-sm font-bold text-[var(--color-fg-default)]">
                              {hyp.title}
                            </h3>
                            <p className="mt-1 text-xs text-[var(--color-fg-muted)] leading-relaxed">
                              {hyp.causal_claim}
                            </p>
                          </div>

                          {hyp.intervention && (
                            <div className="p-2 rounded-[var(--radius-sm)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-muted)] text-[11px] font-mono text-[var(--color-accent-fg)]">
                              <span className="text-[10px] text-[var(--color-fg-muted)] uppercase block font-sans font-semibold mb-0.5">
                                Recommended Intervention:
                              </span>
                              {hyp.intervention}
                            </div>
                          )}

                          <div className="flex items-center justify-between pt-1">
                            <span className="text-[11px] text-[var(--color-fg-muted)]">
                              {hyp.supporting_artifact_ids?.length || 0} supporting artifacts
                            </span>
                            <Button
                              variant={testResult?.status === "CONFIRMED" ? "secondary" : "primary"}
                              size="sm"
                              disabled={isTesting}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleTestHypothesis(hyp);
                              }}
                              className="h-7 text-xs font-medium"
                            >
                              {isTesting
                                ? "Simulating..."
                                : testResult
                                  ? "Re-test Branch"
                                  : "Test in Sandbox"}
                            </Button>
                          </div>

                          {testResult && (
                            <div
                              className={`p-2.5 rounded-[var(--radius-sm)] border text-xs ${
                                testResult.status === "CONFIRMED"
                                  ? "bg-[var(--color-success-muted)]/30 border-[var(--color-success-muted)] text-[var(--color-success-fg)]"
                                  : "bg-[var(--color-danger-muted)]/30 border-[var(--color-danger-muted)] text-[var(--color-danger-fg)]"
                              }`}
                            >
                              <div className="font-semibold">
                                <span>{testResult.message}</span>
                              </div>
                              {testResult.failure_oracle && (
                                <div className="mt-1 text-[11px] opacity-90 font-mono">
                                  Latency:{" "}
                                  {testResult.failure_oracle.avg_total_latency}ms (Budget:{" "}
                                  {testResult.failure_oracle.freshness_budget_ms}ms)
                                </div>
                              )}
                            </div>
                          )}
                        </PanelSection>
                      </Panel>
                    );
                  })}
                </PanelStack>
              )}
            </PanelSection>
          </Panel>
        </div>

        {/* Right: Dynamic Interactive Causal Graph */}
        <div className="space-y-6">
          <Panel padding="none">
            <PanelHeader
              title="Interactive Causal Topology Graph"
              subtitle="Lane DAG derived from the incident's temporal evidence graph"
              divider={true}
            />
            <PanelSection dividerBefore={false}>
              {/* Graph Controls Toolbar - Real functional handlers */}
              <Toolbar
                bordered={true}
                className="mb-4 rounded-[var(--radius-sm)] border border-[var(--color-border-default)]"
              >
                <ToolbarGroup>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Zoom In"
                    onClick={() => setZoom((prev) => Math.min(prev + 15, 200))}
                    className="h-8 w-8 p-0"
                  >
                    <ZoomIn className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Zoom Out"
                    onClick={() => setZoom((prev) => Math.max(prev - 15, 50))}
                    className="h-8 w-8 p-0"
                  >
                    <ZoomOut className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Fit View to Contents"
                    onClick={() => {
                      setZoom(100);
                      setPan({ x: 0, y: 0 });
                    }}
                    className="h-8 w-8 p-0"
                  >
                    <Maximize className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Reset View"
                    onClick={() => {
                      setZoom(100);
                      setPan({ x: 0, y: 0 });
                      setConfidenceThreshold(50);
                      setEvidenceFilter("ALL");
                    }}
                    className="h-8 w-8 p-0"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Toggle Layout Mode"
                    onClick={() =>
                      setLayoutMode((prev) =>
                        prev === "hierarchical" ? "constellation" : "hierarchical"
                      )
                    }
                    className="h-8 px-2 text-xs font-mono"
                  >
                    <Sliders className="h-3.5 w-3.5 mr-1" />
                    {layoutMode}
                  </Button>
                </ToolbarGroup>

                <ToolbarSeparator />

                <ToolbarGroup>
                  <label
                    htmlFor="confidence-threshold"
                    className="text-xs font-medium text-[var(--color-fg-muted)]"
                  >
                    Confidence:
                  </label>
                  <ToolbarItem>
                    <Input
                      id="confidence-threshold"
                      type="number"
                      min={0}
                      max={100}
                      value={confidenceThreshold}
                      onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                      aria-label="Confidence:"
                      className="w-16 h-7 text-xs font-mono text-center"
                    />
                    <span className="text-xs font-mono text-[var(--color-fg-muted)] ml-1">%</span>
                  </ToolbarItem>
                </ToolbarGroup>

                <ToolbarSeparator />

                <ToolbarGroup aria-label="Evidence State Filters">
                  <span className="text-xs font-medium text-[var(--color-fg-muted)] mr-1">
                    Evidence State:
                  </span>
                  {(["ALL", "SUPPORTED", "CONTRADICTED", "UNKNOWN"] as const).map((state) => (
                    <Button
                      key={state}
                      variant={evidenceFilter === state ? "primary" : "ghost"}
                      size="sm"
                      onClick={() => setEvidenceFilter(state)}
                      className="h-7 px-2 text-[11px] font-semibold"
                    >
                      {state}
                    </Button>
                  ))}
                </ToolbarGroup>
              </Toolbar>

              {/* Dynamic Interactive SVG Canvas */}
              {!hasGraph ? (
                <EmptyState
                  icon={EmptyStateIcons.network}
                  title="No causal graph available"
                  description={
                    loading
                      ? "Deriving the temporal evidence graph…"
                      : "The backend has not produced a temporal evidence graph for this incident. Run the investigation pipeline so the timeline, causality analysis, and lane DAG can be derived from real evidence."
                  }
                />
              ) : (
                <div
                  className="w-full h-[460px] bg-[radial-gradient(ellipse_at_top,_var(--color-canvas-inset)_0%,_var(--color-canvas)_85%)] rounded-[var(--radius-lg)] border border-[var(--color-border-default)] overflow-hidden relative cursor-grab active:cursor-grabbing select-none"
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onMouseLeave={handleMouseUp}
                >
                  <div className="absolute top-3 left-3 z-10 flex items-center gap-2 pointer-events-none">
                    <Badge tone="neutral" size="sm">
                      Zoom: {zoom}%
                    </Badge>
                    <Badge tone="neutral" size="sm">
                      Mode: {layoutMode}
                    </Badge>
                    <span className="text-[11px] text-[var(--color-fg-muted)] font-mono">
                      Drag to pan • Click nodes to inspect
                    </span>
                  </div>

                  <svg
                    className="w-full h-full"
                    viewBox="0 0 860 520"
                    preserveAspectRatio="xMidYMid meet"
                    role="img"
                    aria-label={`Causal lane graph with ${laneNodes.length} lanes and ${laneEdges.length} edges`}
                  >
                    <defs>
                      <marker
                        id="arrow-default"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-border-strong)" />
                      </marker>
                      <marker
                        id="arrow-accent"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-accent-fg)" />
                      </marker>
                      <marker
                        id="arrow-danger"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-danger-fg)" />
                      </marker>
                      <marker
                        id="arrow-success"
                        viewBox="0 0 10 10"
                        refX="10"
                        refY="5"
                        markerWidth="6"
                        markerHeight="6"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-success-fg)" />
                      </marker>
                    </defs>

                    <g
                      transform={`translate(${pan.x}, ${pan.y}) scale(${zoom / 100})`}
                      style={{
                        transformOrigin: "430px 260px",
                        transition: isDragging ? "none" : "transform 0.2s ease-out",
                      }}
                    >
                      {/* Render Directed Causal Edges */}
                      {laneEdges.map((edge) => {
                        const src = laneNodes.find((n) => n.id === edge.source);
                        const dst = laneNodes.find((n) => n.id === edge.target);
                        if (!src || !dst) return null;

                        const isConnectedToSelected =
                          src.id === selectedLaneId || dst.id === selectedLaneId;
                        const markerId = edge.dashed
                          ? "url(#arrow-default)"
                          : dst.isSafetyOutcome
                            ? "url(#arrow-danger)"
                            : "url(#arrow-accent)";

                        // Curved Bezier Path
                        const midX = (src.x + dst.x) / 2;
                        const pathD = `M ${src.x + 95} ${src.y} C ${midX} ${src.y}, ${midX} ${dst.y}, ${dst.x - 95} ${dst.y}`;

                        return (
                          <g key={edge.id}>
                            <path
                              d={pathD}
                              fill="none"
                              stroke={
                                dst.isSafetyOutcome
                                  ? "var(--color-danger-fg)"
                                  : "var(--color-accent-fg)"
                              }
                              strokeWidth={isConnectedToSelected ? 2.5 : 1.5}
                              strokeDasharray={edge.dashed ? "4 4" : "none"}
                              strokeOpacity={isConnectedToSelected ? 1.0 : 0.45}
                              markerEnd={markerId}
                            />
                            <text
                              x={midX}
                              y={(src.y + dst.y) / 2 - 6}
                              fontSize="8"
                              textAnchor="middle"
                              fill="var(--color-fg-muted)"
                              fontFamily="var(--font-mono)"
                              opacity={isConnectedToSelected ? 1 : 0.6}
                            >
                              {provenanceLabel(edge.provenance)}
                            </text>
                          </g>
                        );
                      })}

                      {/* Render Graph Nodes */}
                      {laneNodes.map((node) => {
                        const isSelected = selectedLane?.id === node.id;

                        return (
                          <g
                            key={node.id}
                            transform={`translate(${node.x}, ${node.y})`}
                            onClick={() => setSelectedLaneId(node.id)}
                            className="cursor-pointer"
                          >
                            {/* Node Background Pill */}
                            <rect
                              x="-95"
                              y="-22"
                              width="190"
                              height="44"
                              rx="8"
                              fill="var(--color-canvas)"
                              stroke={
                                isSelected
                                  ? "var(--color-accent-fg)"
                                  : node.isSafetyOutcome
                                    ? "var(--color-danger-fg)"
                                    : "var(--color-border-default)"
                              }
                              strokeWidth={isSelected ? 2.5 : 1}
                              className="transition-colors hover:stroke-[var(--color-accent-fg)]"
                            />

                            {/* Status Color Dot */}
                            <circle cx="-76" cy="0" r="5" fill={node.color} />

                            {/* Title Label */}
                            <text
                              x="-62"
                              y="-4"
                              fontSize="11"
                              fontWeight="bold"
                              fill="var(--color-fg-default)"
                              fontFamily="var(--font-sans)"
                            >
                              {node.label.length > 20
                                ? node.label.slice(0, 18) + "…"
                                : node.label}
                            </text>

                            {/* Subtitle / Telemetry */}
                            <text
                              x="-62"
                              y="11"
                              fontSize="9"
                              fill="var(--color-fg-muted)"
                              fontFamily="var(--font-mono)"
                            >
                              {node.subtitle.length > 28
                                ? node.subtitle.slice(0, 26) + "…"
                                : node.subtitle}
                            </text>
                          </g>
                        );
                      })}
                    </g>
                  </svg>
                </div>
              )}

              {/* Real Causal Chain Inspection */}
              <div className="mt-4">
                <Panel
                  variant="inset"
                  padding="md"
                  className="border border-[var(--color-accent-muted)]"
                >
                  <PanelHeader
                    title={
                      activeChain
                        ? `Causal Chain: ${activeChain.terminal_message.slice(0, 60)}`
                        : "Causal Chain"
                    }
                    subtitle={
                      activeChain
                        ? `${activeChain.length} propagation steps terminating in ${activeChain.terminal_lane}`
                        : "Propagation path from source evidence to terminal outcome"
                    }
                    divider={true}
                    actions={
                      safetyChains.length > 1 ? (
                        <Select
                          aria-label="Select causal chain"
                          value={String(selectedChainIndex)}
                          onValueChange={(v) => setSelectedChainIndex(Number(v))}
                          options={safetyChains.map((chain, idx) => ({
                            value: String(idx),
                            label: chain.terminal_message.slice(0, 44),
                          }))}
                          className="h-7 text-xs"
                        />
                      ) : undefined
                    }
                  />
                  {!activeChain ? (
                    <EmptyState
                      icon={EmptyStateIcons.network}
                      title="No propagation chain derived"
                      description="The temporal analyzer did not find a causal path terminating in a safety outcome for this incident."
                      size="sm"
                    />
                  ) : (
                    <div className="space-y-2 text-xs">
                      {activeChain.steps.map((step, idx) => {
                        const isTerminal = idx === activeChain.steps.length - 1;
                        return (
                          <div
                            key={`${step.source}->${step.target}-${idx}`}
                            className="flex items-start gap-2"
                          >
                            <span
                              className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${
                                isTerminal
                                  ? "bg-[var(--color-danger-fg)]"
                                  : step.provenance === "deployment_chain"
                                    ? "bg-[var(--color-attention-fg)]"
                                    : "bg-[var(--color-accent-fg)]"
                              }`}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="font-mono text-[11px] text-[var(--color-accent-fg)]">
                                  {step.target_lane}
                                </span>
                                <span className="font-mono text-[10px] text-[var(--color-fg-subtle)]">
                                  [{provenanceLabel(step.provenance)}]
                                </span>
                                <span className="text-[11px] text-[var(--color-fg-muted)]">
                                  {step.source_message.slice(0, 48)}
                                </span>
                              </div>
                              <div
                                className={`text-[11px] leading-relaxed ${
                                  isTerminal
                                    ? "text-[var(--color-danger-fg)] font-bold"
                                    : "text-[var(--color-fg-muted)]"
                                }`}
                              >
                                {step.target_message}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </Panel>
              </div>

              {/* Lane provenance detail for the selected lane */}
              {selectedLane && (
                <div className="mt-4">
                  <Panel variant="inset" padding="md">
                    <PanelHeader
                      title={`Lane: ${laneLabel(selectedLane.id)}`}
                      subtitle={`Tier ${selectedLane.tier} · ${selectedLane.eventCount} evidence events`}
                      divider={true}
                    />
                    <div className="pt-1">
                      <KV label="Clock Domains" value={selectedLane.domains.join(", ")} />
                      <KV
                        label="Source Artifacts"
                        value={selectedLane.sources.length}
                        sub={selectedLane.sources.join(", ")}
                      />
                      <KV label="Evidence Window" value={formatSpan(selectedLane)} />
                      <KV
                        label="Incoming Edges"
                        value={incomingEdges.length}
                        sub={
                          incomingEdges
                            .map((e) => `${e.source} → ${e.target}`)
                            .join("; ") || "none"
                        }
                      />
                      <KV
                        label="Outgoing Edges"
                        value={outgoingEdges.length}
                        sub={
                          outgoingEdges
                            .map((e) => `${e.source} → ${e.target}`)
                            .join("; ") || "none"
                        }
                      />
                    </div>
                  </Panel>
                </div>
              )}
            </PanelSection>
          </Panel>
        </div>
      </div>
    </div>
  );
}

function formatSpan(lane: { start_s: number; end_s: number }): string {
  const span = lane.end_s - lane.start_s;
  if (span < 1) return `${(span * 1000).toFixed(0)}ms window`;
  return `${span.toFixed(2)}s window`;
}
