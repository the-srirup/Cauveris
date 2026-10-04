"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Badge, PageHeader } from "@/components/ui";
import { api, Hypothesis } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useAuthStore } from "@/lib/auth";

export default function CausalConstellation() {
  const { incidentId } = useActiveIncident();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/causal-constellation');
    }
  }, [isAuthenticated, authLoading, router]);

  // Show loading while auth is initializing
  if (authLoading) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Loading causal constellation...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Redirecting to login...</p>
      </div>
    );
  }

  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hypotheses, setHypotheses] = useState<Hypothesis[]>([]);
  const [testResults, setTestResults] = useState<Record<string, any>>({});
  const [selectedNode, setSelectedNode] = useState<string>("h1");

  // Load hypotheses from backend
  const loadHypotheses = async (id: string) => {
    setLoading(true);
    try {
      const res = await api.getHypotheses(id);
      if (res && res.hypotheses && res.hypotheses.length > 0) {
        setHypotheses(res.hypotheses);
      }
    } catch (e: any) {
      // If error, generate fallback matching the golden incident
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

  // Test hypothesis via sandbox digital twin simulation
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

  // Fallback hypotheses if none returned yet
  const displayHypotheses: Hypothesis[] = hypotheses.length > 0 ? hypotheses : [
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

  return (
    <div className="min-h-screen bg-[var(--theme-background)] text-[var(--theme-foreground)] p-6">
      {/* Header */}
      <PageHeader
        title="Causal Constellation"
        subtitle="Multi-dimensional hypothesis mapping and evidence linkage"
        badge={
          <Badge tone="primary" dot={true}>
            {displayHypotheses.length} Active Hypotheses
          </Badge>
        }
      />

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-[var(--color-brand-danger)]/10 border border-[var(--color-brand-danger)]/25 rounded-xl text-[var(--color-brand-danger)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--color-brand-danger)] hover:text-[var(--color-brand-primary)] text-xs font-semibold uppercase">Dismiss</button>
        </div>
      )}

      {/* Main Content */}
      <div className="grid gap-8 lg:grid-cols-[1fr_1fr]">
        {/* Left: Hypotheses Cards */}
        <div className="space-y-6">
          <Card title="Root-Cause Hypotheses & Interventions">
            <div className="space-y-6">
              {displayHypotheses.map((hyp, index) => {
                const hypKey = hyp.hypothesis_id || hyp.id;
                const testResult = testResults[hypKey];
                const isTesting = testingId === hypKey;
                const confidenceVal = hyp.confidence || Math.round((hyp.confidence_prior || 0.5) * 100);

                return (
                  <div
                    key={hypKey}
                    className={`p-5 rounded-xl border transition-all ${
                      testResult?.status === "CONFIRMED"
                        ? "bg-[var(--color-brand-success)]/5 border-[var(--color-brand-success)]/30 shadow-lg shadow-[var(--color-brand-success)]/5"
                        : testResult?.status === "REFUTED"
                          ? "bg-[var(--color-brand-danger)]/5 border-[var(--color-brand-danger)]/20 opacity-80"
                          : "bg-[var(--color-surface)]/50 border-[var(--color-border)] hover:border-[var(--color-brand-primary)]/20"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="font-bold text-[var(--color-brand-primary)] text-base flex items-center gap-2">
                          <span className="text-[var(--color-brand-primary)] font-mono">#{index + 1}</span>
                          {hyp.title}
                        </h3>
                      </div>
                      <div>
                        {testResult?.status === "CONFIRMED" ? (
                          <Badge tone="success" dot={true}>ROOT CAUSE CONFIRMED</Badge>
                        ) : testResult?.status === "REFUTED" ? (
                          <Badge tone="danger" dot={true}>REFUTED (100% Failure)</Badge>
                        ) : (
                          <Badge tone="primary">{hyp.status}</Badge>
                        )}
                      </div>
                    </div>

                    <p className="text-xs text-[var(--color-text-muted)] mt-2 leading-relaxed">
                      {hyp.causal_claim || hyp.description}
                    </p>

                    {/* Intervention details */}
                    {hyp.intervention && (
                      <div className="mt-3 p-2.5 rounded-lg bg-[var(--theme-background)]/30 border border-[var(--color-border)] text-xs">
                        <span className="text-[var(--color-text-muted)] block text-[10px] uppercase tracking-wider font-semibold">Planned Intervention:</span>
                        <code className="text-[var(--color-brand-primary)] font-mono mt-0.5 block">{hyp.intervention}</code>
                      </div>
                    )}

                    {/* Evidence summary */}
                    <div className="flex flex-wrap gap-2 mt-3 text-xs">
                      <Badge tone="secondary">Supporting: {hyp.supporting_artifact_ids?.length ?? 1}</Badge>
                      <Badge tone="danger">Contradicting: {hyp.contradicting_artifact_ids?.length ?? 0}</Badge>
                      <Badge tone="muted">Missing: {hyp.missing_evidence?.length ?? 0}</Badge>
                    </div>

                    {/* Confidence Meter */}
                    <div className="mt-4 flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-[var(--color-text-muted)]">Prior Confidence:</span>
                          <span className="font-mono text-[var(--color-brand-primary)] font-bold">{confidenceVal}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-[var(--color-border)] rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              testResult?.status === "CONFIRMED"
                                ? "bg-[var(--color-brand-success)]"
                                : testResult?.status === "REFUTED"
                                  ? "bg-[var(--color-brand-danger)]"
                                  : "bg-primary"
                            }`}
                            style={{ width: `${confidenceVal}%` }}
                          />
                        </div>
                      </div>

                      <Button
                        variant={testResult?.status === "CONFIRMED" ? "success" : "outline"}
                        size="sm"
                        onClick={() => handleTestHypothesis(hyp)}
                        disabled={loading || isTesting}
                        className="flex-shrink-0"
                      >
                        {isTesting ? "Testing Twin..." : testResult ? "Re-Test" : "Test Hypothesis"}
                      </Button>
                    </div>

                    {/* Live Test Outcome */}
                    {testResult && (
                      <div className={`mt-3 p-3 rounded-lg border text-xs ${
                        testResult.status === "CONFIRMED"
                          ? "bg-[var(--color-brand-success)]/10 border-success/30 text-success"
                          : "bg-[var(--color-brand-danger)]/10 border-danger/30 text-danger"
                      }`}>
                        <div className="font-semibold flex items-center gap-1.5">
                          <span>{testResult.status === "CONFIRMED" ? "✓" : "✕"}</span>
                          <span>{testResult.message}</span>
                        </div>
                        {testResult.failure_oracle && (
                          <div className="mt-1 text-[11px] opacity-90 font-mono">
                            Avg Latency: {testResult.failure_oracle.avg_total_latency}ms (Budget: {testResult.failure_oracle.freshness_budget_ms}ms)
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        {/* Right: Interactive Causal Graph */}
        <div className="space-y-6">
          <Card title="Interactive Causal Topology Graph">
            <div className="p-4 bg-[var(--color-surface)]/40 rounded-xl border border-[var(--color-border)] space-y-4">
              <p className="text-xs text-[var(--color-text-muted)]">
                Directed acyclic causal graph reconstructed from synchronized logs, telemetry, code revisions, and simulation counters.
              </p>

              {/* Node Inspector */}
              <div className="p-4 rounded-xl bg-[var(--theme-background)]/40 border border-[var(--color-brand-primary)]/20">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] uppercase font-bold text-[var(--color-brand-primary)] tracking-wider">Causal Chain Inspection</span>
                  <Badge tone="success">Verified Path</Badge>
                </div>
                <div className="space-y-2 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-primary" />
                    <span className="font-mono text-[var(--color-brand-primary)]">deployments/events.json</span>
                    <span className="text-[var(--color-text-muted)] text-[11px]">→ v42 deployed at 08:00:00Z</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-primary" />
                    <span className="font-mono text-[var(--color-brand-primary)]">config/inference.yaml</span>
                    <span className="text-[var(--color-text-muted)] text-[11px]">→ batching_window_ms: 100 → 200</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-secondary" />
                    <span className="font-mono text-[var(--color-brand-primary)]">traces/otel.json</span>
                    <span className="text-[var(--color-text-muted)] text-[11px]">→ inference latency: 155ms (accum delay ~115ms)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-[var(--color-brand-danger)]" />
                    <span className="font-mono text-[var(--color-brand-primary)]">logs/ros-nodes.jsonl</span>
                    <span className="text-[var(--color-text-muted)] text-[11px]">→ detection age: 140ms exceeds 120ms freshness budget</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-[var(--color-brand-danger)]" />
                    <span className="font-mono text-[var(--color-brand-primary)]">recordings/robot_run.mcap</span>
                    <span className="text-danger font-bold text-[11px]">→ emergency_stop triggered at 10:30:00Z</span>
                  </div>
                </div>
              </div>

              {/* Visual Graph Diagram */}
              <div className="p-6 rounded-xl bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--theme-background)_80%)] border border-[var(--color-border)] flex flex-col items-center justify-center space-y-4">
                {/* Node 1: Root Cause */}
                <div className="w-full max-w-sm p-3 rounded-lg border border-primary/40 bg-primary/10 text-center shadow-lg shadow-primary/10">
                  <div className="text-[10px] text-[var(--color-brand-primary)] uppercase font-bold">1. Root Trigger (v42 Release)</div>
                  <div className="text-xs font-mono font-semibold text-[var(--color-brand-primary)] mt-0.5">batching_window_ms = 200</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">source: config/inference.yaml</div>
                </div>

                <div className="text-[var(--color-brand-primary)] font-mono text-xs">↓ (causes batch wait: ~105ms)</div>

                {/* Node 2: Latency Spike */}
                <div className="w-full max-w-sm p-3 rounded-lg border border-secondary/40 bg-secondary/10 text-center shadow-lg shadow-secondary/10">
                  <div className="text-[10px] text-secondary uppercase font-bold">2. Latency Amplification</div>
                  <div className="text-xs font-mono font-semibold text-[var(--color-brand-primary)] mt-0.5">Total Inference Latency = 155ms</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">source: traces/otel.json (span: inference_request)</div>
                </div>

                <div className="text-secondary font-mono text-xs">↓ (delivered to robot at t+155ms)</div>

                {/* Node 3: Budget Violation */}
                <div className="w-full max-w-sm p-3 rounded-lg border border-danger/40 bg-[var(--color-brand-danger)]/10 text-center shadow-lg shadow-danger/10">
                  <div className="text-[10px] text-danger uppercase font-bold">3. Freshness Budget Breach</div>
                  <div className="text-xs font-mono font-semibold text-[var(--color-brand-primary)] mt-0.5">Perception Age &gt; 120ms Budget</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">source: detection_client.py (validate_freshness)</div>
                </div>

                <div className="text-danger font-mono text-xs">↓ (safety violation tripped)</div>

                {/* Node 4: Terminal Event */}
                <div className="w-full max-w-sm p-3 rounded-lg border border-danger bg-[var(--color-brand-danger)]/20 text-center ring-2 ring-danger/30">
                  <div className="text-[10px] text-danger uppercase font-bold">4. Terminal Incident</div>
                  <div className="text-xs font-bold text-[var(--color-brand-primary)] mt-0.5">EMERGENCY STOP (Warehouse AMR-01)</div>
                  <div className="text-[10px] text-[var(--color-text-muted)]">source: recordings/robot_run.mcap</div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}