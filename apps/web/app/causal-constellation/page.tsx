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
} from "@/components/ui";
import { ZoomIn, ZoomOut, Maximize, RotateCcw, Sliders, GitBranch, AlertTriangle, Check, ArrowRight, Shield, Play } from "lucide-react";
import {
  api,
  Hypothesis,
  TemporalVisualizationResponse,
} from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { AuthGate } from "@/components/AuthGate";
import {
  InstrumentPanel,
  SignalTag,
  TraceValue,
  HypothesisPlate,
  HypothesisData,
} from "@/design-system";

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
          `${hyp.title}: Confirmed root cause. Failures eliminated in twin.`,
          "success"
        );
      } else {
        notify(
          `${hyp.title}: Refuted. Failures persisted at ${Math.round(
            result.reproduction_rate * 100
          )}% in twin.`,
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

  // Real lane DAG derived from backend with support for both Hierarchical and Constellation modes
  const { laneNodes, laneEdges } = useMemo(() => {
    const rawNodes: LaneNode[] = [];
    const rawEdges: LaneEdge[] = [];

    // Fallback: When backend event lanes are not yet ready, synthesize DAG from evaluated hypotheses
    if (!graph?.lanes?.length) {
      if (!hypotheses.length) return { laneNodes: rawNodes, laneEdges: rawEdges };

      // Root Failure Origin
      rawNodes.push({
        id: "failure-origin",
        label: "Failure Horizon",
        subtitle: "Anomaly Trigger",
        tier: 0,
        x: layoutMode === "constellation" ? 420 : 110,
        y: 250,
        color: "#ffffff",
        eventCount: 1,
        domains: ["ingestion"],
        sources: ["sensor"],
        isSafetyOutcome: false,
        start_s: 0,
        end_s: 0,
      });

      // Terminal Safety Node
      rawNodes.push({
        id: "safety-guardrail",
        label: "Safety Monitor",
        subtitle: "Terminal Interlock",
        tier: 3,
        x: layoutMode === "constellation" ? 420 : 750,
        y: 250,
        color: "#ffffff",
        eventCount: 1,
        domains: ["safety"],
        sources: ["runtime"],
        isSafetyOutcome: true,
        start_s: 0,
        end_s: 0,
      });

      // Hypotheses
      const visibleHyps = hypotheses.slice(0, 4);
      visibleHyps.forEach((hyp, idx) => {
        const hypKey = hyp.hypothesis_id || hyp.id;
        const nSib = visibleHyps.length;
        const yStep = nSib > 1 ? 260 / (nSib - 1) : 0;
        const y = nSib === 1 ? 250 : 120 + idx * yStep;
        const angle = (idx / Math.max(nSib, 1)) * 2 * Math.PI - Math.PI / 2;
        const x = layoutMode === "constellation" ? Math.round(420 + Math.cos(angle) * 160) : 340;
        const constellY = layoutMode === "constellation" ? Math.round(250 + Math.sin(angle) * 110) : y;

        rawNodes.push({
          id: hypKey,
          label: hyp.title.length > 20 ? hyp.title.slice(0, 18) + "…" : hyp.title,
          subtitle: `${Math.round((hyp.confidence_prior ?? 0.5) * 100)}% conf · ${(hyp as any).mechanism || "fault"}`,
          tier: 1,
          x,
          y: constellY,
          color: "#e4e4e7",
          eventCount: hyp.supporting_artifact_ids?.length || 1,
          domains: ["inference"],
          sources: ["reasoning"],
          isSafetyOutcome: false,
          start_s: 0,
          end_s: 0,
        });

        rawEdges.push({
          id: `e-origin-${hypKey}`,
          source: "failure-origin",
          target: hypKey,
          edgeCount: 1,
          provenance: "INFERRED",
          dashed: false,
        });

        if (hyp.intervention) {
          const intId = `int-${hypKey}`;
          const intX = layoutMode === "constellation" ? Math.round(420 + Math.cos(angle) * 260) : 560;
          const intY = layoutMode === "constellation" ? Math.round(250 + Math.sin(angle) * 180) : constellY;
          rawNodes.push({
            id: intId,
            label: "Intervention",
            subtitle: hyp.intervention.length > 22 ? hyp.intervention.slice(0, 20) + "…" : hyp.intervention,
            tier: 2,
            x: intX,
            y: intY,
            color: "#a1a1aa",
            eventCount: 1,
            domains: ["repair"],
            sources: ["twin"],
            isSafetyOutcome: false,
            start_s: 0,
            end_s: 0,
          });

          rawEdges.push({
            id: `e-${hypKey}-${intId}`,
            source: hypKey,
            target: intId,
            edgeCount: 1,
            provenance: "DERIVED",
            dashed: false,
          });

          rawEdges.push({
            id: `e-${intId}-safety`,
            source: intId,
            target: "safety-guardrail",
            edgeCount: 1,
            provenance: "VERIFIED",
            dashed: true,
          });
        } else {
          rawEdges.push({
            id: `e-${hypKey}-safety`,
            source: hypKey,
            target: "safety-guardrail",
            edgeCount: 1,
            provenance: "INFERRED",
            dashed: true,
          });
        }
      });

      return { laneNodes: rawNodes, laneEdges: rawEdges };
    }

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
    const maxTier = tiers.length > 0 ? tiers[tiers.length - 1] : 0;

    if (layoutMode === "constellation") {
      // Radial Constellation Layout centered on the safety outcome / terminal lane
      const centerLane = graph.lanes.find((l) => safetyLanes.has(l.lane)) || graph.lanes[graph.lanes.length - 1];
      const otherLanes = graph.lanes.filter((l) => l.lane !== centerLane.lane);

      // Terminal node at center
      const centerIsSafety = safetyLanes.has(centerLane.lane);
      rawNodes.push({
        id: centerLane.lane,
        label: laneLabel(centerLane.lane),
        subtitle: `${centerLane.event_count} events · ${centerLane.domains.join(" + ")}`,
        tier: centerLane.tier,
        x: 420,
        y: 250,
        color: centerIsSafety ? "#ffffff" : "#d4d4d8",
        eventCount: centerLane.event_count,
        domains: centerLane.domains,
        sources: centerLane.sources,
        isSafetyOutcome: centerIsSafety,
        start_s: centerLane.start_s,
        end_s: centerLane.end_s,
      });

      // Distribute surrounding nodes in orbital rings by tier
      otherLanes.forEach((lane, idx) => {
        const tierDist = Math.max(1, Math.abs(lane.tier - centerLane.tier));
        const ringRadiusX = 110 + tierDist * 85;
        const ringRadiusY = 75 + tierDist * 55;
        const angle = (idx / Math.max(otherLanes.length, 1)) * 2 * Math.PI - Math.PI / 2;

        const x = Math.round(420 + Math.cos(angle) * ringRadiusX);
        const y = Math.round(250 + Math.sin(angle) * ringRadiusY);
        const isSafety = safetyLanes.has(lane.lane);

        rawNodes.push({
          id: lane.lane,
          label: laneLabel(lane.lane),
          subtitle: `${lane.event_count} events · ${lane.domains.join(" + ")}`,
          tier: lane.tier,
          x,
          y,
          color: isSafety ? "#ffffff" : "#a1a1aa",
          eventCount: lane.event_count,
          domains: lane.domains,
          sources: lane.sources,
          isSafetyOutcome: isSafety,
          start_s: lane.start_s,
          end_s: lane.end_s,
        });
      });
    } else {
      // Hierarchical Topological DAG Layout with bounded spacing
      const numTiers = tiers.length;
      const xStep = numTiers > 1 ? 620 / (numTiers - 1) : 0;
      const xByTier = new Map<number, number>();
      tiers.forEach((tier, idx) => {
        xByTier.set(tier, numTiers === 1 ? 420 : 110 + idx * xStep);
      });

      graph.lanes.forEach((lane) => {
        const siblings = byTier.get(lane.tier) ?? [lane];
        const idx = siblings.indexOf(lane);
        const nSib = siblings.length;
        const yStep = nSib > 1 ? 300 / (nSib - 1) : 0;
        const y = nSib === 1 ? 250 : 90 + idx * yStep;
        const isSafety = safetyLanes.has(lane.lane);
        const domainLabel = lane.domains.join(" + ");

        rawNodes.push({
          id: lane.lane,
          label: laneLabel(lane.lane),
          subtitle: `${lane.event_count} events · ${domainLabel}`,
          tier: lane.tier,
          x: xByTier.get(lane.tier) ?? 420,
          y,
          color: isSafety ? "#ffffff" : "#a1a1aa",
          eventCount: lane.event_count,
          domains: lane.domains,
          sources: lane.sources,
          isSafetyOutcome: isSafety,
          start_s: lane.start_s,
          end_s: lane.end_s,
        });
      });
    }

    (graph.lane_edges ?? []).forEach((edge: any, idx: number) => {
      const prov = typeof edge.provenance === "object" ? Object.keys(edge.provenance || {})[0] : (edge.primary_provenance || "OBSERVED");
      rawEdges.push({
        id: `e-${idx}-${edge.source || edge.source_lane}-${edge.target || edge.target_lane}`,
        source: edge.source || edge.source_lane,
        target: edge.target || edge.target_lane,
        edgeCount: edge.edge_count,
        provenance: prov,
        dashed: prov === "temporal_proximity",
      });
    });

    return { laneNodes: rawNodes, laneEdges: rawEdges };
  }, [graph, layoutMode]);

  // Visible hypotheses based on confidence threshold & evidence filter
  const visibleHypotheses = useMemo(() => {
    return hypotheses.filter((hyp) => {
      const hypKey = hyp.hypothesis_id || hyp.id;
      const conf = Math.round(
        (hyp.confidence_prior ?? (hyp.confidence ? hyp.confidence / 100 : 0.5)) * 100
      );
      if (conf < confidenceThreshold) return false;

      const testResult = testResults[hypKey];
      if (evidenceFilter === "SUPPORTED") {
        return testResult?.status === "CONFIRMED" || conf >= 75;
      }
      if (evidenceFilter === "CONTRADICTED") {
        return testResult?.status === "REFUTED";
      }
      if (evidenceFilter === "UNKNOWN") {
        return !testResult && conf < 75;
      }
      return true;
    });
  }, [hypotheses, confidenceThreshold, evidenceFilter, testResults]);

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

  const summary = graph?.summary;

  return (
    <div className="w-full space-y-5">
      {/* Standard Page Header */}
      <PageHeader
        title="Hypotheses"
        ariaLabel="Causal Constellation"
        subtitle="Causal graph topology & hypothesis evaluation for robotic system failures"
        breadcrumbs={[{ label: "Overview", href: "/" }, { label: "Hypotheses" }]}
        badge={
          <div className="flex items-center gap-2">
            <Badge tone="neutral" size="sm">INFERRED</Badge>
            <Badge tone="info" size="sm">
              {hypotheses.length} Evaluated
            </Badge>
          </div>
        }
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1 border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] p-1 rounded-[var(--radius-md,6px)]">
              <Button
                variant="ghost"
                size="sm"
                aria-label="Zoom In"
                onClick={() => setZoom((prev) => Math.min(prev + 15, 200))}
                className="h-7 w-7 p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Zoom Out"
                onClick={() => setZoom((prev) => Math.max(prev - 15, 50))}
                className="h-7 w-7 p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Fit View to Contents"
                onClick={() => {
                  setZoom(100);
                  setPan({ x: 0, y: 0 });
                }}
                className="h-7 w-7 p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <Maximize className="h-3.5 w-3.5" />
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
                className="h-7 w-7 p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <RotateCcw className="h-3.5 w-3.5" />
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
                className="h-7 w-7 p-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                <Sliders className="h-3.5 w-3.5" />
              </Button>
            </div>

            {/* Confidence Slider */}
            <div className="flex items-center gap-2 px-2.5 py-1 border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] rounded-[var(--radius-md,6px)] text-xs">
              <label htmlFor="confidence-threshold-input" className="text-[var(--color-fg-muted,#5f6b76)] text-xs font-medium">
                Confidence:
              </label>
              <input
                id="confidence-threshold-input"
                aria-label="Confidence:"
                type="range"
                min="0"
                max="100"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                className="w-16 accent-[var(--color-accent,#0969da)]"
              />
              <span className="tabular-nums font-mono text-[var(--color-fg-default,#1f2933)] font-semibold text-xs">
                {confidenceThreshold}%
              </span>
            </div>

            {/* Evidence State Filter Buttons */}
            <div className="flex items-center border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] rounded-[var(--radius-md,6px)] text-xs p-0.5">
              <span className="px-2 text-[var(--color-fg-muted,#5f6b76)]">State:</span>
              {(["ALL", "SUPPORTED", "CONTRADICTED", "UNKNOWN"] as const).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setEvidenceFilter(filter)}
                  className={`px-2 py-0.5 rounded-[var(--radius-sm,4px)] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                    evidenceFilter === filter
                      ? "bg-[var(--color-canvas-default,#ffffff)] shadow-xs text-[var(--color-fg-default,#1f2933)] font-semibold"
                      : "text-[var(--color-fg-muted,#5f6b76)] hover:text-[var(--color-fg-default,#1f2933)]"
                  }`}
                >
                  {filter}
                </button>
              ))}
            </div>
          </div>
        }
      />

      {/* Error Banner */}
      {error && (
        <div className="p-3 bg-zinc-900 border border-zinc-700 rounded-[2px] flex items-center justify-between text-xs text-zinc-300">
          <span>{error}</span>
          <button
            onClick={() => setError(null)}
            className="text-xs uppercase font-bold text-zinc-400 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Real Graph Summary Strip */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <TraceValue
            label="Evidence Nodes"
            value={summary.total_events}
            unit="events"
            provenance="OBSERVED"
            source="Timeline Graph Engine"
          />
          <TraceValue
            label="Causal Edges"
            value={summary.causal_edge_count}
            unit="relations"
            provenance="DERIVED"
            source="Provenance Rules"
          />
          <TraceValue
            label="Propagation Chains"
            value={summary.chain_count}
            unit="chains"
            provenance="INFERRED"
            source="Cross-Domain Tracer"
          />
          <TraceValue
            label="Temporal Anomalies"
            value={summary.anomaly_count}
            unit="deviations"
            provenance="CALIBRATED"
            uncertainty={`${Math.round(summary.confidence * 100)}%`}
          />
        </div>
      )}

      {/* Main Split Workbench: Left Hypotheses + Right Interactive Causal DAG */}
      <div className="grid grid-cols-12 gap-3 min-h-[580px]">
        {/* Left: Ranked Causal Hypotheses (Col 5) */}
        <div className="col-span-12 lg:col-span-5 flex flex-col space-y-3">
          <InstrumentPanel
            title="Falsifiable Causal Hypotheses"
            subtitle="Ranked by Bayesian prior confidence. Test in twin to verify."
          >
            {visibleHypotheses.length === 0 ? (
              <div className="p-6 text-center text-xs text-[var(--text-tertiary,#71717a)] italic">
                No hypotheses match current confidence and evidence filters.
              </div>
            ) : (
              <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
                {visibleHypotheses.map((hyp, idx) => {
                  const hypKey = hyp.hypothesis_id || hyp.id;
                  const isSelected = selectedNode === hypKey;
                  const isTesting = testingId === hypKey;
                  const testResult = testResults[hypKey];
                  const conf = Math.round(
                    (hyp.confidence_prior ?? (hyp.confidence ? hyp.confidence / 100 : 0.5)) * 100
                  );

                  return (
                    <div
                      key={hypKey}
                      className="relative flex flex-col"
                      onClick={() => setSelectedNode(hypKey)}
                    >
                      <HypothesisPlate
                        hypothesis={{
                          id: hypKey,
                          rank: idx + 1,
                          mechanism: (hyp as any).mechanism || hyp.title || "system_fault",
                          title: hyp.title,
                          causalClaim: hyp.causal_claim || (hyp as any).description || hyp.title || "",
                          confidence: conf / 100,
                          supportingEvidence: hyp.supporting_artifact_ids || ["1 evidence file"],
                          contradictoryEvidence: testResult?.status === "REFUTED" ? ["Replay failure persisted"] : [],
                          missingEvidence: [],
                          canSimulate: true,
                          canRepair: true,
                          proposedIntervention: hyp.intervention,
                        }}
                        selected={isSelected}
                        onSimulate={() => handleTestHypothesis(hyp)}
                      />

                      {/* Sandbox test button & result readout */}
                      <div className="mt-1 flex items-center justify-between px-2 text-xs">
                        {testResult ? (
                          <span
                            className={`text-[11px] font-bold ${
                              testResult.status === "CONFIRMED" ? "text-zinc-100" : "text-zinc-400"
                            }`}
                          >
                            {testResult.status}: {testResult.message}
                          </span>
                        ) : (
                          <span className="text-[10px] text-[var(--text-tertiary,#71717a)]">
                            Falsifiable in Digital Twin
                          </span>
                        )}

                        <Button
                          variant={testResult?.status === "CONFIRMED" ? "primary" : "outline"}
                          size="sm"
                          disabled={isTesting}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleTestHypothesis(hyp);
                          }}
                          className="h-6 text-[10px] px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                        >
                          {isTesting ? "Simulating..." : testResult ? "Re-test" : "Test in Twin"}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </InstrumentPanel>
        </div>

        {/* Right: Dynamic SVG Causal Graph (Col 7) */}
        <div className="col-span-12 lg:col-span-7 flex flex-col">
          <InstrumentPanel
            title="Interactive Causal Topology DAG"
            subtitle="Derived cross-domain propagation paths with verified timebounds"
            className="flex-1 flex flex-col"
            bodyClassName="p-0 flex-1 flex flex-col"
          >
            <div
              className="relative w-full flex-1 min-h-[500px] overflow-hidden bg-[var(--color-canvas-inset,#f8f9fa)] dark:bg-[#0d1117] cursor-grab active:cursor-grabbing"
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
            >
              {laneNodes.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full min-h-[460px] p-6 text-center">
                  <GitBranch className="w-8 h-8 text-zinc-500 mb-2.5" />
                  <span className="text-xs font-bold uppercase text-zinc-200">Causal Topology Ingestion Standby</span>
                  <p className="text-[11px] text-[var(--text-tertiary,#71717a)] max-w-sm mt-1">
                    No causal DAG data loaded for this incident yet. Start investigation to compute temporal cross-domain pathways.
                  </p>
                </div>
              ) : (
                <svg
                  className="w-full h-full select-none"
                  viewBox="0 0 840 500"
                  preserveAspectRatio="xMidYMid meet"
                >
                  <defs>
                    <marker
                      id="causal-arrow"
                      viewBox="0 0 10 10"
                      refX="16"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-fg-muted, #5f6b76)" />
                    </marker>
                    <marker
                      id="causal-arrow-active"
                      viewBox="0 0 10 10"
                      refX="16"
                      refY="5"
                      markerWidth="6"
                      markerHeight="6"
                      orient="auto-start-reverse"
                    >
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--color-accent, #0969da)" />
                    </marker>
                  </defs>

                  <g
                    transform={`translate(${pan.x}, ${pan.y}) scale(${zoom / 100})`}
                    style={{ transformOrigin: "420px 250px" }}
                  >
                    {/* Constellation mode orbital concentric rings */}
                    {layoutMode === "constellation" && (
                      <>
                        <ellipse cx="420" cy="250" rx="195" ry="130" fill="none" stroke="var(--color-border-default, #d9e0e7)" strokeWidth="1" strokeDasharray="4 4" opacity="0.7" />
                        <ellipse cx="420" cy="250" rx="300" ry="195" fill="none" stroke="var(--color-border-default, #d9e0e7)" strokeWidth="1" strokeDasharray="4 4" opacity="0.4" />
                      </>
                    )}

                    {/* Edges */}
                    {laneEdges.map((edge) => {
                      const src = laneNodes.find((n) => n.id === edge.source);
                      const tgt = laneNodes.find((n) => n.id === edge.target);
                      if (!src || !tgt) return null;

                      const isSelected = selectedLaneId === edge.source || selectedLaneId === edge.target || selectedNode === edge.source || selectedNode === edge.target;

                      return (
                        <line
                          key={edge.id}
                          x1={src.x}
                          y1={src.y}
                          x2={tgt.x}
                          y2={tgt.y}
                          stroke={isSelected ? "var(--color-accent, #0969da)" : "var(--color-border-default, #d9e0e7)"}
                          strokeWidth={isSelected ? 2 : 1}
                          strokeDasharray={edge.dashed ? "4 4" : undefined}
                          markerEnd={isSelected ? "url(#causal-arrow-active)" : "url(#causal-arrow)"}
                          opacity={isSelected ? 1 : 0.65}
                          className="transition-colors"
                        />
                      );
                    })}

                    {/* Nodes */}
                    {laneNodes.map((node) => {
                      const isSelected = selectedLaneId === node.id || selectedNode === node.id || (selectedNode && node.id.includes(selectedNode));
                      const isSafety = node.isSafetyOutcome;

                      return (
                        <g
                          key={node.id}
                          transform={`translate(${node.x}, ${node.y})`}
                          onClick={() => {
                            setSelectedLaneId(node.id);
                            const matchingHyp = hypotheses.find((h) => (h.hypothesis_id || h.id) === node.id);
                            if (matchingHyp) {
                              setSelectedNode(matchingHyp.hypothesis_id || matchingHyp.id);
                            }
                          }}
                          className="cursor-pointer transition-transform duration-100 hover:scale-105"
                        >
                          {/* Safety outcome alarm halo */}
                          {isSafety && (
                            <circle
                              r={18}
                              fill="none"
                              stroke="#d4d4d8"
                              strokeWidth={1.5}
                              strokeDasharray="3 3"
                              className="animate-pulse"
                            />
                          )}

                          {/* Selection ring */}
                          {isSelected && (
                            <circle
                              r={16}
                              fill="none"
                              stroke="#fafafa"
                              strokeWidth={2}
                            />
                          )}

                          {/* Node Shape */}
                          <circle
                            r={11}
                            fill={isSafety ? "rgba(218, 54, 51, 0.2)" : isSelected ? "rgba(31, 111, 235, 0.25)" : "var(--color-canvas-subtle, #161b22)"}
                            stroke={isSafety ? "var(--color-danger-emphasis, #da3633)" : isSelected ? "var(--color-accent-emphasis, #1f6feb)" : "var(--color-border-default, #30363d)"}
                            strokeWidth={isSafety ? 2 : 1.5}
                          />

                          {/* Node label */}
                          <text
                            y={22}
                            textAnchor="middle"
                            fill={isSelected ? "var(--color-accent, #0969da)" : "var(--color-fg-default, #1f2933)"}
                            fontSize={10}
                            fontFamily="inherit"
                            className="select-none pointer-events-none font-semibold"
                          >
                            {node.label}
                          </text>
                          <text
                            y={32}
                            textAnchor="middle"
                            fill="var(--color-fg-muted, #5f6b76)"
                            fontSize={8.5}
                            fontFamily="inherit"
                            className="select-none pointer-events-none"
                          >
                            {node.eventCount} evs
                          </text>
                        </g>
                      );
                    })}
                  </g>
                </svg>
              )}

              {/* Bottom graph legend */}
              <div className="absolute bottom-3 left-3 flex items-center gap-4 bg-[var(--color-canvas-default,#ffffff)]/95 p-2 border border-[var(--color-border-default,#d9e0e7)] text-[10px] text-[var(--text-tertiary,#71717a)] rounded-[2px]">
                <span className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Domain Lane
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-2.5 h-2.5 rounded-full border border-rose-400 bg-rose-200 inline-block" /> Safety Outcome Terminal
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 border-t border-dashed border-slate-400 inline-block" /> Temporal Proximity
                </span>
              </div>
            </div>
          </InstrumentPanel>
        </div>
      </div>
    </div>
  );
}
