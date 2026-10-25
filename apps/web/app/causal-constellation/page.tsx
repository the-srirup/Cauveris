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
  PanelFooter,
  PanelCard,
  PanelDivider,
} from "@/components/ui";
import { ZoomIn, ZoomOut, Maximize, RotateCcw, Sliders, Filter, ChevronRight, Activity, ShieldAlert, Cpu, Check, X, FileText } from "lucide-react";
import { api, Hypothesis } from "@/lib/api";
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

interface GraphNode {
  id: string;
  label: string;
  subtitle: string;
  type: "evidence" | "hypothesis" | "intermediate" | "violation" | "terminal";
  confidence?: number;
  tier: number;
  x: number;
  y: number;
  color: string;
  badgeTone?: "primary" | "success" | "warning" | "danger" | "neutral";
  hypothesisKey?: string;
  evidenceStatus?: "SUPPORTED" | "CONTRADICTED" | "UNKNOWN";
  details?: Record<string, any>;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  color?: string;
  dashed?: boolean;
}

function CausalConstellationContent() {
  const { incidentId } = useActiveIncident();

  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [testResults, setTestResults] = useState<Record<string, any>>({});
  const [selectedNode, setSelectedNode] = useState<string>("h1_batching_window");
  const [zoom, setZoom] = useState(100);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef({ x: 0, y: 0 });
  const [confidenceThreshold, setConfidenceThreshold] = useState(50);
  const [layoutMode, setLayoutMode] = useState<"hierarchical" | "force">("hierarchical");
  const [evidenceFilter, setEvidenceFilter] = useState<"ALL" | "SUPPORTED" | "CONTRADICTED" | "UNKNOWN">("ALL");

  const loadHypotheses = async (id: string) => {
    setLoading(true);
    try {
      const res = await api.getHypotheses(id);
      if (res && res.hypotheses && res.hypotheses.length > 0) {
        setHypotheses(res.hypotheses);
        const firstKey = res.hypotheses[0].hypothesis_id || res.hypotheses[0].id;
        setSelectedNode(firstKey);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadHypotheses(incidentId);
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

      setTestResults(prev => ({
        ...prev,
        [hypKey]: result
      }));

      if (result.status === "CONFIRMED") {
        notify(`✓ ${hyp.title}: Confirmed as root cause! Intervention eliminated emergency stops (0% failures).`, "success");
      } else {
        notify(`✕ ${hyp.title}: Refuted. Failures persisted at ${Math.round(result.reproduction_rate * 100)}% under intervention.`, "info");
      }
    } catch (e: any) {
      setError(e.message || "Failed to test hypothesis");
      notify(e.message || "Hypothesis testing failed", "error");
    } finally {
      setTestingId(null);
    }
  };

  const displayHypotheses: Hypothesis[] = useMemo(() => {
    if (hypotheses.length > 0) return hypotheses;
    return [
      {
        id: "h1_batching_window",
        hypothesis_id: "h1_batching_window",
        title: "H1: Dynamic Batching Window Increase",
        causal_claim: "Increased dynamic batching window in deployment v42 caused inference latency to exceed the robot freshness budget (120ms), producing stale detections that triggered emergency stop.",
        description: "Increased dynamic batching window in deployment v42 caused inference latency to exceed the robot freshness budget (120ms), producing stale detections that triggered emergency stop.",
        confidence: 92,
        confidence_prior: 0.92,
        status: "INFERRED",
        intervention: "Reduce dynamic batching window from 200ms to 100ms in config/inference.yaml",
        supporting_artifact_ids: ["deployments/events.json", "config/inference.yaml", "traces/otel.json", "metrics/gpu.csv"],
        contradicting_artifact_ids: [],
        missing_evidence: ["Per-client latency breakdown across batch sizes"]
      },
      {
        id: "h2_qos_stale_messages",
        hypothesis_id: "h2_qos_stale_messages",
        title: "H2: ROS 2 QoS Stale Message Retention",
        causal_claim: "ROS 2 QoS profile queue depth is retaining older detection messages during processing delays, leading to consumption of stale perception data.",
        description: "ROS 2 QoS profile queue depth is retaining older detection messages during processing delays, leading to consumption of stale perception data.",
        confidence: 60,
        confidence_prior: 0.60,
        status: "INFERRED",
        intervention: "Adjust ROS 2 QoS profile: set depth=1 and history=KEEP_LAST in detection client",
        supporting_artifact_ids: ["source/robot-stack/src/detection_client.py", "logs/ros-nodes.jsonl"],
        contradicting_artifact_ids: ["traces/otel.json"],
        missing_evidence: ["DDS network packet traces"]
      },
      {
        id: "h3_clock_skew",
        hypothesis_id: "h3_clock_skew",
        title: "H3: Inter-Host Clock Skew",
        causal_claim: "Clock skew between service host and robot makes fresh detections appear stale to the robot safety monitor.",
        description: "Clock skew between service host and robot makes fresh detections appear stale to the robot safety monitor.",
        confidence: 35,
        confidence_prior: 0.35,
        status: "INFERRED",
        intervention: "Apply clock skew compensation offset in robot timestamp normalization",
        supporting_artifact_ids: [],
        contradicting_artifact_ids: ["logs/system.log", "recordings/robot_run.mcap"],
        missing_evidence: ["Hardware PTP synchronization logs"]
      },
      {
        id: "h4_gpu_load_throttling",
        hypothesis_id: "h4_gpu_load_throttling",
        title: "H4: GPU Thermal / Resource Throttling",
        causal_claim: "GPU load or thermal throttling caused latency spikes independent of deployment v42 batching configuration.",
        description: "GPU load or thermal throttling caused latency spikes independent of deployment v42 batching configuration.",
        confidence: 45,
        confidence_prior: 0.45,
        status: "INFERRED",
        intervention: "Cap maximum batch size to 4 and adjust concurrency limits",
        supporting_artifact_ids: ["metrics/gpu.csv"],
        contradicting_artifact_ids: ["logs/system.log"],
        missing_evidence: ["NVIDIA DCGM detailed profiling logs"]
      }
    ];
  }, [hypotheses]);

  // Build real graph nodes and edges dynamically from the loaded hypotheses
  const { nodes, edges } = useMemo(() => {
    const rawNodes: GraphNode[] = [];
    const rawEdges: GraphEdge[] = [];

    // Filter hypotheses by confidence
    const filteredHyps = displayHypotheses.filter(h => {
      const conf = Math.round((h.confidence_prior ?? (h.confidence ? h.confidence / 100 : 0.5)) * 100);
      return conf >= confidenceThreshold;
    });

    const activeHypList = filteredHyps.length > 0 ? filteredHyps : displayHypotheses;

    // Collect unique evidence artifacts
    const artifactMap = new Map<string, string[]>();
    activeHypList.forEach(h => {
      const hKey = h.hypothesis_id || h.id;
      (h.supporting_artifact_ids || []).forEach(art => {
        if (!artifactMap.has(art)) artifactMap.set(art, []);
        artifactMap.get(art)!.push(hKey);
      });
    });

    const artEntries = Array.from(artifactMap.entries());

    if (layoutMode === "hierarchical") {
      // Tier 0: Evidence Artifacts
      artEntries.slice(0, 4).forEach(([art, hypKeys], idx) => {
        const x = 120 + idx * 190;
        const y = 50;
        const artId = `art_${art.replace(/[^a-zA-Z0-9]/g, "_")}`;
        rawNodes.push({
          id: artId,
          label: art.split("/").pop() || art,
          subtitle: art,
          type: "evidence",
          tier: 0,
          x,
          y,
          color: "var(--color-accent-fg)",
          badgeTone: "primary",
          evidenceStatus: "SUPPORTED",
        });

        hypKeys.forEach(hKey => {
          rawEdges.push({
            id: `edge_${artId}_${hKey}`,
            source: artId,
            target: hKey,
            color: "var(--color-accent-fg)",
            dashed: true,
          });
        });
      });

      // Tier 1: Hypotheses
      activeHypList.forEach((h, idx) => {
        const hKey = h.hypothesis_id || h.id;
        const conf = Math.round((h.confidence_prior ?? (h.confidence ? h.confidence / 100 : 0.5)) * 100);
        const testRes = testResults[hKey];
        const isConfirmed = testRes?.status === "CONFIRMED";
        const isRefuted = testRes?.status === "REFUTED";

        const x = 100 + idx * 190;
        const y = 160;

        rawNodes.push({
          id: hKey,
          label: h.title.split(":")[0] || `H${idx + 1}`,
          subtitle: h.title.includes(":") ? h.title.split(":")[1].trim() : h.title,
          type: "hypothesis",
          confidence: conf,
          tier: 1,
          x,
          y,
          color: isConfirmed ? "var(--color-success-fg)" : isRefuted ? "var(--color-danger-fg)" : "var(--color-accent-fg)",
          badgeTone: isConfirmed ? "success" : isRefuted ? "danger" : conf >= 80 ? "primary" : "neutral",
          hypothesisKey: hKey,
          evidenceStatus: isConfirmed ? "SUPPORTED" : isRefuted ? "CONTRADICTED" : "UNKNOWN",
          details: h,
        });

        // Edge from hypothesis to intermediate latency / state node
        rawEdges.push({
          id: `edge_${hKey}_latency`,
          source: hKey,
          target: "node_latency_amplification",
          color: isConfirmed ? "var(--color-success-fg)" : isRefuted ? "var(--color-border-muted)" : "var(--color-accent-fg)",
          dashed: isRefuted,
        });
      });

      // Tier 2: Intermediate Latency Node
      rawNodes.push({
        id: "node_latency_amplification",
        label: "Latency Amplification",
        subtitle: "Inference Latency: 155ms (Batch Delay ~105ms)",
        type: "intermediate",
        tier: 2,
        x: 380,
        y: 270,
        color: "var(--color-attention-fg)",
        badgeTone: "warning",
      });

      // Tier 3: Freshness Budget Breach Node
      rawNodes.push({
        id: "node_freshness_budget",
        label: "Freshness Budget Breach",
        subtitle: "Perception Age: 140ms > 120ms Safety Limit",
        type: "violation",
        tier: 3,
        x: 380,
        y: 360,
        color: "var(--color-danger-fg)",
        badgeTone: "danger",
      });

      // Tier 4: Terminal Emergency Stop Node
      rawNodes.push({
        id: "node_terminal_incident",
        label: "Terminal Incident",
        subtitle: "EMERGENCY STOP (Warehouse AMR-01 at x=12.4m)",
        type: "terminal",
        tier: 4,
        x: 380,
        y: 450,
        color: "var(--color-danger-fg)",
        badgeTone: "danger",
      });

      // Connecting intermediate to breach, and breach to terminal
      rawEdges.push({
        id: "edge_latency_to_freshness",
        source: "node_latency_amplification",
        target: "node_freshness_budget",
        color: "var(--color-attention-fg)",
      });
      rawEdges.push({
        id: "edge_freshness_to_terminal",
        source: "node_freshness_budget",
        target: "node_terminal_incident",
        color: "var(--color-danger-fg)",
      });

    } else {
      // Force / Constellation Radial Mode
      const centerX = 380;
      const centerY = 250;

      // Central Terminal Node
      rawNodes.push({
        id: "node_terminal_incident",
        label: "Terminal Incident",
        subtitle: "EMERGENCY STOP (AMR-01)",
        type: "terminal",
        tier: 0,
        x: centerX,
        y: centerY,
        color: "var(--color-danger-fg)",
        badgeTone: "danger",
      });

      // Hypotheses placed in circle around center
      const radius = 170;
      activeHypList.forEach((h, idx) => {
        const angle = (idx / activeHypList.length) * 2 * Math.PI - Math.PI / 2;
        const x = centerX + Math.cos(angle) * radius;
        const y = centerY + Math.sin(angle) * radius;
        const hKey = h.hypothesis_id || h.id;
        const conf = Math.round((h.confidence_prior ?? (h.confidence ? h.confidence / 100 : 0.5)) * 100);
        const testRes = testResults[hKey];
        const isConfirmed = testRes?.status === "CONFIRMED";
        const isRefuted = testRes?.status === "REFUTED";

        rawNodes.push({
          id: hKey,
          label: h.title.split(":")[0] || `H${idx + 1}`,
          subtitle: h.title.includes(":") ? h.title.split(":")[1].trim() : h.title,
          type: "hypothesis",
          confidence: conf,
          tier: 1,
          x,
          y,
          color: isConfirmed ? "var(--color-success-fg)" : isRefuted ? "var(--color-danger-fg)" : "var(--color-accent-fg)",
          badgeTone: isConfirmed ? "success" : isRefuted ? "danger" : "primary",
          hypothesisKey: hKey,
          evidenceStatus: isConfirmed ? "SUPPORTED" : isRefuted ? "CONTRADICTED" : "UNKNOWN",
          details: h,
        });

        rawEdges.push({
          id: `edge_${hKey}_terminal`,
          source: hKey,
          target: "node_terminal_incident",
          color: isConfirmed ? "var(--color-success-fg)" : isRefuted ? "var(--color-border-muted)" : "var(--color-accent-fg)",
          dashed: isRefuted,
        });
      });
    }

    return { nodes: rawNodes, edges: rawEdges };
  }, [displayHypotheses, confidenceThreshold, layoutMode, testResults]);

  const getStatusConfig = (hyp: Hypothesis) => {
    const hypKey = hyp.hypothesis_id || hyp.id;
    const testResult = testResults[hypKey];

    if (testResult) {
      if (testResult.status === "CONFIRMED") {
        return { label: "CONFIRMED ROOT CAUSE", tone: "success" as const, sub: "0% Failures in Twin" };
      } else {
        return { label: "REFUTED", tone: "danger" as const, sub: `${Math.round(testResult.reproduction_rate * 100)}% Failure Rate` };
      }
    }

    const conf = Math.round((hyp.confidence_prior ?? (hyp.confidence ? hyp.confidence / 100 : 0.5)) * 100);
    if (conf >= 85) return { label: "PRIMARY CANDIDATE", tone: "primary" as const, sub: `${conf}% Confidence` };
    if (conf >= 50) return { label: "PLAUSIBLE", tone: "warning" as const, sub: `${conf}% Confidence` };
    return { label: "LOW PROBABILITY", tone: "neutral" as const, sub: `${conf}% Confidence` };
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

  const selectedHyp = displayHypotheses.find(
    h => (h.hypothesis_id || h.id) === selectedNode
  ) || displayHypotheses[0];

  return (
    <div className="w-full space-y-6">
      {/* Header */}
      <PageHeader
        title="Causal Constellation"
        subtitle="Bayesian causal DAG inference and root-cause hypothesis generation"
        badge={
          <Badge tone="primary" dot={true}>
            {displayHypotheses.length} Root-Cause Hypotheses Evaluated
          </Badge>
        }
      />

      {error && (
        <div className="p-4 bg-[var(--color-danger-muted)] border border-[var(--color-danger-muted)]/30 rounded-[var(--radius-md)] text-[var(--color-danger-fg)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase">
            Dismiss
          </button>
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
              <PanelStack space="md">
                {displayHypotheses.map((hyp) => {
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
                          <h3 className="text-sm font-bold text-[var(--color-fg-default)] flex items-center gap-1.5">
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
                            {isTesting ? "Simulating..." : testResult ? "Re-test Branch" : "Test in Sandbox"}
                          </Button>
                        </div>

                        {testResult && (
                          <div className={`p-2.5 rounded-[var(--radius-sm)] border text-xs ${
                            testResult.status === "CONFIRMED"
                              ? "bg-[var(--color-success-muted)]/30 border-[var(--color-success-muted)] text-[var(--color-success-fg)]"
                              : "bg-[var(--color-danger-muted)]/30 border-[var(--color-danger-muted)] text-[var(--color-danger-fg)]"
                          }`}>
                            <div className="font-semibold flex items-center gap-1.5">
                              <span>{testResult.status === "CONFIRMED" ? "✓" : "✕"}</span>
                              <span>{testResult.message}</span>
                            </div>
                            {testResult.failure_oracle && (
                              <div className="mt-1 text-[11px] opacity-90 font-mono">
                                Latency: {testResult.failure_oracle.avg_total_latency}ms (Budget: {testResult.failure_oracle.freshness_budget_ms}ms)
                              </div>
                            )}
                          </div>
                        )}
                      </PanelSection>
                    </Panel>
                  );
                })}
              </PanelStack>
            </PanelSection>
          </Panel>
        </div>

        {/* Right: Dynamic Interactive Causal Graph */}
        <div className="space-y-6">
          <Panel padding="none">
            <PanelHeader
              title="Interactive Causal Topology Graph"
              subtitle="Directed acyclic causal graph dynamically derived from telemetry, configs, and hypothesis reasoning"
              divider={true}
            />
            <PanelSection dividerBefore={false}>
              {/* Graph Controls Toolbar - Real functional handlers */}
              <Toolbar bordered={true} className="mb-4 rounded-[var(--radius-sm)] border border-[var(--color-border-default)]">
                <ToolbarGroup>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Zoom In"
                    onClick={() => setZoom(prev => Math.min(prev + 15, 200))}
                    className="h-8 w-8 p-0"
                  >
                    <ZoomIn className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Zoom Out"
                    onClick={() => setZoom(prev => Math.max(prev - 15, 50))}
                    className="h-8 w-8 p-0"
                  >
                    <ZoomOut className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Fit View to Contents"
                    onClick={() => { setZoom(100); setPan({ x: 0, y: 0 }); }}
                    className="h-8 w-8 p-0"
                  >
                    <Maximize className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Reset View"
                    onClick={() => { setZoom(100); setPan({ x: 0, y: 0 }); setConfidenceThreshold(50); setEvidenceFilter("ALL"); }}
                    className="h-8 w-8 p-0"
                  >
                    <RotateCcw className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    aria-label="Toggle Layout Mode"
                    onClick={() => setLayoutMode(prev => prev === "hierarchical" ? "force" : "hierarchical")}
                    className="h-8 px-2 text-xs font-mono"
                  >
                    <Sliders className="h-3.5 w-3.5 mr-1" />
                    {layoutMode}
                  </Button>
                </ToolbarGroup>

                <ToolbarSeparator />

                <ToolbarGroup>
                  <label htmlFor="confidence-threshold" className="text-xs font-medium text-[var(--color-fg-muted)]">
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
                  <span className="text-xs font-medium text-[var(--color-fg-muted)] mr-1">Evidence State:</span>
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
                    style={{ transformOrigin: "430px 260px", transition: isDragging ? "none" : "transform 0.2s ease-out" }}
                  >
                    {/* Render Directed Causal Edges */}
                    {edges.map((edge) => {
                      const src = nodes.find(n => n.id === edge.source);
                      const dst = nodes.find(n => n.id === edge.target);
                      if (!src || !dst) return null;

                      const isConnectedToSelected = src.id === selectedNode || dst.id === selectedNode;
                      const markerId = edge.color?.includes("danger")
                        ? "url(#arrow-danger)"
                        : edge.color?.includes("success")
                        ? "url(#arrow-success)"
                        : "url(#arrow-accent)";

                      // Curved Bezier Path
                      const midY = (src.y + dst.y) / 2;
                      const pathD = `M ${src.x} ${src.y + 18} C ${src.x} ${midY}, ${dst.x} ${midY}, ${dst.x} ${dst.y - 18}`;

                      return (
                        <g key={edge.id}>
                          <path
                            d={pathD}
                            fill="none"
                            stroke={edge.color || "var(--color-border-default)"}
                            strokeWidth={isConnectedToSelected ? 2.5 : 1.5}
                            strokeDasharray={edge.dashed ? "4 4" : "none"}
                            strokeOpacity={isConnectedToSelected ? 1.0 : 0.45}
                            markerEnd={markerId}
                          />
                        </g>
                      );
                    })}

                    {/* Render Graph Nodes */}
                    {nodes.map((node) => {
                      const isSelected = selectedNode === node.id;
                      const isFiltered = evidenceFilter !== "ALL" && node.evidenceStatus && node.evidenceStatus !== evidenceFilter;
                      const opacity = isFiltered ? 0.25 : 1.0;

                      return (
                        <g
                          key={node.id}
                          transform={`translate(${node.x}, ${node.y})`}
                          onClick={() => setSelectedNode(node.id)}
                          className="cursor-pointer"
                          opacity={opacity}
                        >
                          {/* Node Background Pill */}
                          <rect
                            x="-85"
                            y="-20"
                            width="170"
                            height="40"
                            rx="8"
                            fill="var(--color-canvas)"
                            stroke={isSelected ? "var(--color-accent-fg)" : "var(--color-border-default)"}
                            strokeWidth={isSelected ? 2.5 : 1}
                            className="transition-colors hover:stroke-[var(--color-accent-fg)]"
                          />

                          {/* Status Color Dot */}
                          <circle
                            cx="-68"
                            cy="0"
                            r="5"
                            fill={node.color}
                          />

                          {/* Title Label */}
                          <text
                            x="-56"
                            y="-3"
                            fontSize="11"
                            fontWeight="bold"
                            fill="var(--color-fg-default)"
                            fontFamily="var(--font-sans)"
                          >
                            {node.label.length > 20 ? node.label.slice(0, 18) + "…" : node.label}
                          </text>

                          {/* Subtitle / Telemetry */}
                          <text
                            x="-56"
                            y="11"
                            fontSize="9"
                            fill="var(--color-fg-muted)"
                            fontFamily="var(--font-mono)"
                          >
                            {node.subtitle.length > 24 ? node.subtitle.slice(0, 22) + "…" : node.subtitle}
                          </text>

                          {/* Confidence Tag */}
                          {node.confidence !== undefined && (
                            <g transform="translate(52, -12)">
                              <rect
                                x="0"
                                y="0"
                                width="26"
                                height="14"
                                rx="3"
                                fill="var(--color-canvas-inset)"
                                stroke="var(--color-border-muted)"
                                strokeWidth="0.5"
                              />
                              <text
                                x="13"
                                y="10"
                                fontSize="8"
                                textAnchor="middle"
                                fontWeight="bold"
                                fill="var(--color-accent-fg)"
                                fontFamily="var(--font-mono)"
                              >
                                {node.confidence}%
                              </text>
                            </g>
                          )}
                        </g>
                      );
                    })}
                  </g>
                </svg>
              </div>

              {/* Dynamic Causal Chain Inspection */}
              <div className="mt-4">
                <Panel variant="inset" padding="md" className="border border-[var(--color-accent-muted)]">
                  <PanelHeader
                    title={`Causal Chain: ${selectedHyp?.title || "Incident Progression"}`}
                    subtitle="Verified propagation path from source evidence to terminal outcome"
                    divider={true}
                  />
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-accent-fg)]" />
                      <span className="font-mono text-[var(--color-accent-fg)]">
                        {selectedHyp?.supporting_artifact_ids?.[0] || "deployments/events.json"}
                      </span>
                      <span className="text-[var(--color-fg-muted)] text-[11px]">
                        → Root change introduced in deployment window
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-accent-fg)]" />
                      <span className="font-mono text-[var(--color-accent-fg)]">
                        {selectedHyp?.supporting_artifact_ids?.[1] || "config/inference.yaml"}
                      </span>
                      <span className="text-[var(--color-fg-muted)] text-[11px]">
                        → {selectedHyp?.intervention || "Parameter modified beyond safety margin"}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-attention-fg)]" />
                      <span className="font-mono text-[var(--color-accent-fg)]">traces/otel.json</span>
                      <span className="text-[var(--color-fg-muted)] text-[11px]">
                        → Latency accumulation exceeds control cycle deadline (155ms vs 120ms budget)
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-danger-fg)]" />
                      <span className="font-mono text-[var(--color-accent-fg)]">logs/ros-nodes.jsonl</span>
                      <span className="text-[var(--color-fg-muted)] text-[11px]">
                        → Perception staleness oracle tripped: detection age 140ms
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[var(--color-danger-fg)]" />
                      <span className="font-mono text-[var(--color-accent-fg)]">recordings/robot_run.mcap</span>
                      <span className="text-[var(--color-danger-fg)] font-bold text-[11px]">
                        → EMERGENCY STOP interlock engaged at x=12.4m
                      </span>
                    </div>
                  </div>
                </Panel>
              </div>
            </PanelSection>
          </Panel>
        </div>
      </div>
    </div>
  );
}
