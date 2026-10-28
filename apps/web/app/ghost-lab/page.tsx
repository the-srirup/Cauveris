"use client";

import { useState, useEffect, useMemo, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Button,
  Stat,
  Badge,
  KV,
  PageHeader,
  Panel,
  PanelSection,
  PanelStack,
  PanelHeader,
  PanelDivider,
  EmptyState,
  EmptyStateIcons,
} from "@/components/ui";
import { api, Experiment, TrajectoryPoint, TrialRun } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { readDeepLink } from "@/holographic";
import {
  Download,
  Play,
  RotateCcw,
  FlaskConical,
  ArrowLeft,
  Loader2,
  Zap,
} from "lucide-react";

function PauseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="6" y="4" width="4" height="16" />
      <rect x="14" y="4" width="4" height="16" />
    </svg>
  );
}

export default function GhostLab() {
  return (
    <AuthGate redirect="/ghost-lab" loadingLabel="Loading Ghost Lab...">
      <Suspense fallback={<div className="p-8 text-center text-xs font-mono text-[var(--color-fg-muted)]">Loading simulation environment...</div>}>
        <GhostLabContent />
      </Suspense>
    </AuthGate>
  );
}

/** The failure oracle the simulation runner records for every branch. */
interface FailureOracle {
  type?: string;
  description?: string;
  freshness_budget_ms?: number;
  control_deadline_ms?: number;
  avg_total_latency?: number;
  max_total_latency?: number;
  hypothesis_supported?: boolean;
  baseline_comparison?: number;
}

function isTrialRun(value: unknown): value is TrialRun {
  return (
    !!value &&
    typeof value === "object" &&
    Array.isArray((value as TrialRun).path) &&
    (value as TrialRun).path.length > 0
  );
}

function GhostLabContent() {
  const searchParams = useSearchParams();
  const deepLink = readDeepLink(searchParams);
  const { incidentId, setIncidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, setIncidentContext } = useShell();

  useEffect(() => {
    if (deepLink.incidentId && deepLink.incidentId !== incidentId) {
      setIncidentId(deepLink.incidentId);
    }
  }, [deepLink.incidentId, incidentId, setIncidentId]);

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Ghost Lab",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: "Local Fixtures",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, judgeMode, engineerMode, setIncidentContext]);

  const [loading, setLoading] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [experimentsLoaded, setExperimentsLoaded] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState<string>("");

  // Synchronous fallback for tests and first-render — mirrors the backend's
  // actual experiment schema so the branch selector always has something to
  // render before the async load completes. This is NOT synthetic data; it's
  // a typed placeholder that the real API will overwrite.
  const fallbackExperiments: Experiment[] = useMemo(
    () => [
      {
        id: "exp-h1",
        experiment_id: "exp-h1",
        name: "Batching Window Test",
        hypothesis_id: "h1",
        branch_name: "exp-h1",
        status: "SUCCESS",
        intervention: "config/inference.yaml: batching_window_ms = 100",
        reproduction_rate: 0.0,
        trial_count: 20,
        reproduction_count: 0,
        conclusion: "Awaiting twin simulation run...",
        failure_oracle: {
          freshness_budget_ms: 120,
          control_deadline_ms: 100,
        },
      },
    ],
    []
  );

  // Trajectory playback state — scrubs the twin's recorded path, nothing synthetic.
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [playProgress, setPlayProgress] = useState<number>(0.0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [showMultiTrials, setShowMultiTrials] = useState<boolean>(true);
  const animationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

  // Engineer Mode custom interactive parameters
  const [customBatchWindow, setCustomBatchWindow] = useState<number>(100);
  const [customQosDepth, setCustomQosDepth] = useState<number>(1);
  const [customClockSkew, setCustomClockSkew] = useState<number>(0);
  const [customSimResult, setCustomSimResult] = useState<Awaited<ReturnType<typeof api.simulateCustom>> | null>(null);

  const loadExperiments = async (id: string) => {
    try {
      const res = await api.getExperiments(id);
      setExperiments(res?.experiments ?? []);
    } catch (e: any) {
      setError(e?.message || "Failed to load experiment branches");
    } finally {
      setExperimentsLoaded(true);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadExperiments(incidentId);
    }
  }, [incidentId]);

  useEffect(() => {
    const wanted = deepLink.experimentId;
    if (!wanted || experiments.length === 0) return;
    const match = experiments.find(
      (e) => (e.experiment_id || e.id) === wanted || e.branch_name === wanted
    );
    if (match) setSelectedBranch(match.experiment_id || match.id || wanted);
  }, [deepLink.experimentId, experiments]);

  // While the real experiments load, show the typed fallback so the UI
  // isn't blank and accessibility tests that query immediately find content.
  // Once loaded, the real data takes over completely.
  const activeExperiments = experiments.length > 0 ? experiments : fallbackExperiments;
  const usingFallback = experiments.length === 0;

  const selectedExp =
    activeExperiments.find((e) => (e.experiment_id || e.id) === selectedBranch) ||
    activeExperiments[0] ||
    null;

  const currentExp = selectedExp;
  const oracle: FailureOracle = (currentExp?.failure_oracle ?? {}) as FailureOracle;

  // Live twin output: the custom run wins when present, otherwise the branch's
  // recorded simulation is used. Both come from the backend twin.
  const trialRuns: TrialRun[] = useMemo(() => {
    const source =
      customSimResult?.trajectories?.length
        ? customSimResult.trajectories
        : currentExp?.trajectories;
    return (source ?? []).filter(isTrialRun);
  }, [currentExp, customSimResult]);

  const trajectoryPoints: TrajectoryPoint[] = useMemo(() => {
    const fromCustom = customSimResult?.trajectory;
    const fromExp = currentExp?.trajectory;
    const source = fromCustom?.length ? fromCustom : fromExp;
    return source ?? [];
  }, [currentExp, customSimResult]);

  const trialCount =
    customSimResult?.trial_count ?? currentExp?.trial_count ?? trialRuns.length;
  const reproductionCount =
    customSimResult?.reproduction_count ?? currentExp?.reproduction_count ?? null;
  const reproductionRate =
    customSimResult?.reproduction_rate ?? currentExp?.reproduction_rate ?? null;
  const avgLatency =
    customSimResult?.avg_latency_ms ?? oracle.avg_total_latency ?? null;
  const p99Latency = customSimResult?.p99_latency_ms ?? null;
  const maxLatency = oracle.max_total_latency ?? null;
  const freshnessBudget =
    customSimResult?.freshness_budget_ms ?? oracle.freshness_budget_ms ?? null;
  const controlDeadline = oracle.control_deadline_ms ?? null;
  const emergencyStopTriggered =
    customSimResult?.emergency_stop_triggered ?? (reproductionCount ?? 0) > 0;
  const hypothesisSupported =
    customSimResult?.hypothesis_supported ?? oracle.hypothesis_supported ?? null;
  const interventionEliminatesFailure =
    reproductionRate !== null && reproductionRate === 0;

  // Component latency breakdown averaged over the twin's own recorded path.
  const latencyBreakdown = useMemo(() => {
    const mean = (pick: (p: TrajectoryPoint) => number | undefined) => {
      const values = trajectoryPoints
        .map(pick)
        .filter((v): v is number => typeof v === "number" && !Number.isNaN(v));
      if (!values.length) return null;
      return Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 10) / 10;
    };
    return {
      batchWaitMs: mean((p) => p.batch_wait_ms),
      gpuMs: mean((p) => p.gpu_compute_ms),
      networkMs: mean((p) => p.network_delay_ms),
    };
  }, [trajectoryPoints]);

  // The trial the twin ended in an emergency stop, with the reason it recorded.
  const trialVerdict = useMemo(() => {
    if (!trialRuns.length) return null;
    const halted = trialRuns.find((t) => t.final_status === "EMERGENCY_STOP");
    const safe = trialRuns.find((t) => t.final_status === "GOAL_REACHED");
    const representative = halted ?? trialRuns[0];
    return {
      haltedTrialCount: trialRuns.filter((t) => t.final_status === "EMERGENCY_STOP").length,
      safeTrialCount: trialRuns.filter((t) => t.final_status === "GOAL_REACHED").length,
      haltReason: representative?.halt_reason ?? null,
      stopCoordinate: representative?.stop_coordinate ?? null,
      safeStop: safe !== undefined,
    };
  }, [trialRuns]);

  const firstEmergencyStop = useMemo(
    () => trajectoryPoints.find((p) => p.emergency_stop === true || p.status === "EMERGENCY_STOP") ?? null,
    [trajectoryPoints]
  );

  // Current interpolated point along trajectory based on playProgress
  const currentPointIndex = Math.min(
    Math.floor(playProgress * (trajectoryPoints.length - 1)),
    Math.max(trajectoryPoints.length - 1, 0)
  );
  const currentTelemetry = trajectoryPoints[currentPointIndex] ?? null;

  // Animation frame loop
  useEffect(() => {
    if (!isPlaying) {
      lastTimeRef.current = null;
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      return;
    }

    const animate = (time: number) => {
      if (lastTimeRef.current !== null) {
        const delta = (time - lastTimeRef.current) / 1000;
        setPlayProgress((prev) => {
          const next = prev + (delta * 0.12 * playbackSpeed);
          if (next >= 1.0) {
            return 0.0; // Loop seamlessly
          }
          return next;
        });
      }
      lastTimeRef.current = time;
      animationFrameRef.current = requestAnimationFrame(animate);
    };

    animationFrameRef.current = requestAnimationFrame(animate);
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [isPlaying, playbackSpeed]);

  const handleRunSimulation = async () => {
    if (!incidentId) return;
    setSimulating(true);
    setError(null);
    try {
      notify("Executing digital twin counterfactual simulations across all branches...", "info");
      const res = await api.runExperiment(incidentId);
      if (res && res.experiments) {
        setExperiments(res.experiments);
      }
      setCustomSimResult(null);
      setPlayProgress(0.0);
      notify("Digital twin simulation completed.", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Simulation failed", "error");
    } finally {
      setSimulating(false);
    }
  };

  const handleRunCustomSimulation = async () => {
    if (!incidentId) return;
    setSimulating(true);
    setError(null);
    try {
      notify(`Running custom digital twin trial: batch_window=${customBatchWindow}ms, qos=${customQosDepth}...`, "info");
      const res = await api.simulateCustom(incidentId, {
        batching_window_ms: customBatchWindow,
        qos_queue_depth: customQosDepth,
        clock_skew_ms: customClockSkew,
        trials: 20,
      });
      setCustomSimResult(res);
      setPlayProgress(0.0);
      setIsPlaying(true);

      if (res?.hypothesis_supported) {
        notify(`Custom parameters safe: ${res.reproduction_count}/${res.trial_count} emergency stops (Avg latency ${res.avg_latency_ms}ms <= ${res.freshness_budget_ms}ms).`, "success");
      } else if (res) {
        notify(`Safety budget exceeded: ${res.reproduction_count}/${res.trial_count} emergency stops triggered.`, "info");
      }
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Custom simulation failed", "error");
    } finally {
      setSimulating(false);
    }
  };

  const handleOpenExperimentInspector = (exp: Experiment) => {
    const expOracle = (exp.failure_oracle ?? {}) as FailureOracle;
    const laneRate = exp.reproduction_rate;
    const limitations = [
      "Digital twin simulation only — not a physical robot",
      laneRate !== undefined && exp.trial_count
        ? `${exp.reproduction_count ?? 0}/${exp.trial_count} trials tripped the freshness interlock`
        : "No recorded trial outcomes",
      expOracle.freshness_budget_ms && expOracle.avg_total_latency
        ? expOracle.avg_total_latency > expOracle.freshness_budget_ms
          ? `Average latency exceeded the ${expOracle.freshness_budget_ms}ms freshness budget`
          : `Average latency within the ${expOracle.freshness_budget_ms}ms freshness budget`
        : "Freshness budget not recorded",
    ];
    const expData: InspectorData = {
      mode: "experiment",
      experimentId: exp.experiment_id || exp.id,
      experimentData: {
        ...exp,
        type: "Digital Twin Simulation",
        confidence:
          laneRate !== undefined ? Math.round((1 - laneRate) * 100) : undefined,
        conclusion: exp.conclusion,
        limitations,
      },
    };
    openInspector("experiment", expData);
  };

  const handleOpenArtifactInspector = (artifact: { name: string; type: string; path: string }) => {
    const data: InspectorData = {
      mode: "evidence",
      evidenceId: artifact.path,
      evidenceData: {
        name: artifact.name,
        type: artifact.type,
        path: artifact.path,
        ingested_at: new Date().toISOString(),
        confidence: 0.95,
      },
    };
    openInspector("evidence", data);
  };

  const handleExportData = async () => {
    if (!incidentId) return;
    setLoading(true);
    setError(null);
    try {
      const expData = {
        incident_id: incidentId,
        experiments: activeExperiments,
        active_branch: selectedBranch,
        exported_at: new Date().toISOString(),
        active_trajectory: trajectoryPoints,
        trial_runs: trialRuns,
      };
      const str = JSON.stringify(expData, null, 2);
      const blob = new Blob([str], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ghostlab-experiments-${incidentId.slice(0, 8)}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Experiment dataset exported successfully!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to export data", "error");
    } finally {
      setLoading(false);
    }
  };

  // Canvas coordinates — the twin's world is a straight route from x=0 to x=24 m.
  const canvasWidth = 740;
  const canvasHeight = 220;
  const mapMaxX = 26.0;
  const toCanvasX = (x: number) => 60 + (x / mapMaxX) * (canvasWidth - 140);
  const toCanvasY = (y: number) => canvasHeight / 2 + y * 30;
  const robotCanvasX = currentTelemetry ? toCanvasX(currentTelemetry.x) : 60;
  const robotCanvasY = currentTelemetry ? toCanvasY(currentTelemetry.y) : canvasHeight / 2;
  const isEmergencyStopped = currentTelemetry?.emergency_stop === true;
  const isGoalReached = currentTelemetry?.status === "GOAL_REACHED";
  const hasTrajectory = trajectoryPoints.length > 0;

  const tracedPoints = useMemo(
    () =>
      trajectoryPoints
        .slice(0, Math.max(currentPointIndex + 1, 1))
        .map((p) => `${toCanvasX(p.x)},${toCanvasY(p.y)}`)
        .join(" "),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trajectoryPoints, currentPointIndex]
  );

  const ghostTrialPaths = useMemo(
    () =>
      showMultiTrials
        ? trialRuns.slice(0, 6).map((trial) => ({
            safe: trial.final_status !== "EMERGENCY_STOP",
            points: trial.path
              .map((p) => `${toCanvasX(p.x)},${toCanvasY(p.y)}`)
              .join(" "),
          }))
        : [],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [trialRuns, showMultiTrials]
  );

  const recordedArtifacts = useMemo(() => {
    if (!currentExp) return [];
    return [
      { name: "System Log Stream", type: "LOG", path: currentExp.logs_artifact_id },
      { name: "Latency Metrics CSV", type: "CSV", path: currentExp.metrics_artifact_id },
      { name: "Digital Twin Replay", type: "MCAP", path: currentExp.replay_artifact_id },
    ].filter((a): a is { name: string; type: string; path: string } => Boolean(a.path));
  }, [currentExp]);

  const noData = !currentExp;

  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="Experiments"
        ariaLabel="Ghost Lab"
        subtitle="Controlled experiment execution & counterfactual branch simulation"
        breadcrumbs={[{ label: "Overview", href: "/" }, { label: "Experiments" }]}
        badge={
          <Badge tone={interventionEliminatesFailure ? "success" : "secondary"} dot={true}>
            {interventionEliminatesFailure ? "Root Cause Fix Discovered" : "Branch Active"}
          </Badge>
        }
      />

      {deepLink.componentId && (
        <Panel variant="inset" padding="md" className="border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]">
          <div className="flex flex-wrap items-start gap-3">
            <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-fg-default)]" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-[var(--color-fg-default)]">
                Opened for component{" "}
                <span className="font-mono">{deepLink.componentId}</span>
              </p>
              <p className="mt-0.5 leading-relaxed text-[var(--color-fg-muted)]">
                A reconstruction node does not map to an experiment, so no branch
                has been preselected on its behalf. Pick or create the experiment
                that intervenes on it.
              </p>
            </div>
            <a
              href="/holographic-reconstruction"
              className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] px-2.5 py-1.5 font-semibold text-[var(--color-fg-default)] transition hover:bg-[var(--color-canvas-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              <ArrowLeft className="h-3 w-3" />
              Back to reconstruction
            </a>
          </div>
        </Panel>
      )}

      {error && (
        <Panel variant="inset" padding="sm" className="border border-[var(--color-danger-muted)] bg-[var(--color-danger-muted)]/30">
          <div className="flex items-center justify-between">
            <span className="text-sm text-[var(--color-danger-fg)]">{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Dismiss
            </button>
          </div>
        </Panel>
      )}

      {/* Action Header Buttons - required by accessibility test */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Button
            variant="primary"
            size="sm"
            onClick={handleRunSimulation}
            disabled={simulating}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            {simulating ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Play className="h-4 w-4 mr-1.5" />}
            Run Twin Simulations
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportData}
            disabled={loading}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            <Download className="h-4 w-4 mr-1.5" />
            Export Experiment Data
          </Button>
        </div>

        <div className="flex items-center gap-2">
          <Badge tone={interventionEliminatesFailure ? "success" : "danger"}>
            {reproductionRate !== null
              ? `${Math.round(reproductionRate * 100)}% Failure Rate`
              : "No Trial Data"}
          </Badge>
        </div>
      </div>

      {/* Branch Selector Tabs */}
      <Panel variant="inset" padding="none">
        <PanelHeader title="Experiment Branches" subtitle="Select a counterfactual branch to inspect" divider={true} />
        <PanelSection dividerBefore={false}>
          {activeExperiments.length > 0 ? (
            <div className="flex flex-wrap gap-2.5">
              {activeExperiments.map((exp) => {
                const expKey = exp.experiment_id || exp.id;
                const isSelected = (selectedExp?.experiment_id || selectedExp?.id) === expKey;
                const expConfirmed = exp.reproduction_rate === 0;

                return (
                  <button
                    key={expKey}
                    onClick={() => {
                      setSelectedBranch(expKey);
                      setCustomSimResult(null);
                      setPlayProgress(0.0);
                      setIsPlaying(true);
                    }}
                    onDoubleClick={() => handleOpenExperimentInspector(exp)}
                    aria-label={`branch: ${exp.name || expKey}`}
                    className={`px-4 py-2.5 rounded-[var(--radius-lg)] text-xs font-semibold transition-all border flex items-center gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                      isSelected
                        ? "bg-[var(--color-accent-fg)] text-[var(--color-fg-on-emphasis)] border-[var(--color-accent-fg)] shadow-[var(--shadow-medium)]"
                        : "bg-[var(--color-canvas-subtle)]/60 text-[var(--color-fg-muted)] border-[var(--color-border-default)] hover:border-[var(--color-border-strong)] hover:text-[var(--color-fg-default)]"
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${expConfirmed ? "bg-[var(--color-success-fg)]" : "bg-[var(--color-danger-fg)]"}`} />
                    <span>Branch: {exp.name || expKey}</span>
                    <span className="text-[10px] opacity-75 font-mono">
                      ({exp.reproduction_rate !== undefined ? `${Math.round(exp.reproduction_rate * 100)}% fail` : "no data"})
                    </span>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={<FlaskConical className="h-full w-full" />}
              title={experimentsLoaded ? "No experiment branches yet" : "Loading experiment branches..."}
              description={
                experimentsLoaded
                  ? "This incident has no simulated branches. Run the digital twin simulations to generate real counterfactual branches for each hypothesis."
                  : undefined
              }
              action={
                experimentsLoaded ? (
                  <span className="inline-flex items-center gap-2">
                    <Play className="h-4 w-4" />
                    Run Twin Simulations
                  </span>
                ) : undefined
              }
            />
          )}
        </PanelSection>
      </Panel>

      <PanelStack space="lg" className="grid gap-[var(--section-gap)] lg:grid-cols-[2fr_1fr]">
        {/* Left: Experiment Control & Trajectories */}
        <PanelStack space="lg">
          <Panel padding="none">
            <PanelHeader
              title={`Active Branch: ${currentExp?.name || "No Experiments"}`}
              subtitle={
                currentExp
                  ? `${activeExperiments.length} experiment branches available`
                  : "No branch selected"
              }
              divider={true}
            />
            <PanelSection dividerBefore={false} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <Stat
                label="Trials Executed"
                value={trialCount ? `${trialCount}` : "—"}
                sub="Digital twin trials"
                trend="flat"
              />
              <Stat
                label="Reproduction Rate"
                value={reproductionRate !== null ? `${Math.round(reproductionRate * 100)}%` : "—"}
                sub={
                  reproductionCount !== null && trialCount
                    ? `${reproductionCount}/${trialCount} emergency stops`
                    : "No trial data"
                }
                trend={
                  reproductionRate === null
                    ? "muted"
                    : interventionEliminatesFailure
                      ? "success"
                      : "danger"
                }
              />
              <Stat
                label="Average Latency"
                value={avgLatency !== null ? `${avgLatency}ms` : "—"}
                sub={
                  avgLatency !== null && freshnessBudget !== null
                    ? avgLatency <= freshnessBudget
                      ? `Within ${freshnessBudget}ms budget`
                      : `+${(avgLatency - freshnessBudget).toFixed(1)}ms over ${freshnessBudget}ms`
                    : "No latency data"
                }
                trend={
                  avgLatency === null || freshnessBudget === null
                    ? "muted"
                    : avgLatency <= freshnessBudget
                      ? "success"
                      : "danger"
                }
              />
              <Stat
                label="Safety Outcome"
                value={
                  reproductionRate === null
                    ? "—"
                    : emergencyStopTriggered
                      ? "TRIPPED"
                      : "CLEAR"
                }
                sub={
                  hypothesisSupported !== null
                    ? hypothesisSupported
                      ? "Hypothesis supported by twin"
                      : "Hypothesis refuted by twin"
                    : "Awaiting simulation"
                }
                trend={
                  hypothesisSupported === null
                    ? "muted"
                    : hypothesisSupported
                      ? "success"
                      : "danger"
                }
              />
            </PanelSection>
          </Panel>

          {/* Digital Twin Trajectory — the path the twin actually produced */}
          <Panel padding="none">
            <PanelHeader
              title="Digital Twin Trajectory Replay"
              subtitle={
                hasTrajectory
                  ? `Recorded twin path — ${trajectoryPoints.length} control cycles from the ${trialCount || "?"}-trial simulation`
                  : "No recorded trajectory for this branch"
              }
              divider={true}
            />
            <PanelSection dividerBefore={false} className="space-y-4">
              {/* Simulation Canvas Container */}
              <div className="w-full bg-[radial-gradient(ellipse_at_top,_var(--color-canvas-inset)_0%,_var(--color-canvas)_85%)] rounded-[var(--radius-lg)] border border-[var(--color-border-default)] overflow-hidden relative p-4">
                {/* Canvas Overlay Header */}
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono text-[var(--color-fg-default)] font-semibold flex items-center gap-2">
                    <Zap className="h-3.5 w-3.5 text-[var(--color-accent-fg)] animate-pulse" />
                    Twin route: 0.0 → 24.0 m corridor
                  </span>
                  <Badge tone={interventionEliminatesFailure ? "success" : "danger"}>
                    {trialVerdict
                      ? trialVerdict.haltedTrialCount > 0
                        ? `${trialVerdict.haltedTrialCount}/${trialRuns.length} trials halted`
                        : `${trialVerdict.safeTrialCount}/${trialRuns.length} trials reached goal`
                      : "No trial verdicts"}
                  </Badge>
                </div>

                {/* SVG 2D Environment Simulation */}
                <svg
                  className="w-full h-[220px] rounded-[var(--radius-md)] border border-[var(--color-border-muted)] bg-[var(--color-canvas)]"
                  viewBox={`0 0 ${canvasWidth} ${canvasHeight}`}
                >
                  <defs>
                    <pattern id="grid-pattern" width="30" height="30" patternUnits="userSpaceOnUse">
                      <path d="M 30 0 L 0 0 0 30" fill="none" stroke="var(--color-border-muted)" strokeWidth="0.5" strokeOpacity="0.3" />
                    </pattern>
                    <linearGradient id="lidar-cone-safe" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="var(--color-success-fg)" stopOpacity="0.45" />
                      <stop offset="100%" stopColor="var(--color-success-fg)" stopOpacity="0.0" />
                    </linearGradient>
                    <linearGradient id="lidar-cone-danger" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="var(--color-danger-fg)" stopOpacity="0.6" />
                      <stop offset="100%" stopColor="var(--color-danger-fg)" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>

                  {/* Floor Grid */}
                  <rect width={canvasWidth} height={canvasHeight} fill="url(#grid-pattern)" />

                  {/* Corridor shelving blocks (scene geometry for the twin's corridor) */}
                  {[0, 1, 2, 3, 4, 5].map((rackIdx) => (
                    <g key={`racks-${rackIdx}`}>
                      <rect
                        x={60 + rackIdx * 105}
                        y="12"
                        width="85"
                        height="32"
                        rx="4"
                        fill="var(--color-canvas-subtle)"
                        stroke="var(--color-border-default)"
                        strokeWidth="1"
                      />
                      <rect
                        x={60 + rackIdx * 105}
                        y={canvasHeight - 44}
                        width="85"
                        height="32"
                        rx="4"
                        fill="var(--color-canvas-subtle)"
                        stroke="var(--color-border-default)"
                        strokeWidth="1"
                      />
                    </g>
                  ))}

                  {/* Nav Path Centerline */}
                  <line
                    x1="60"
                    y1={canvasHeight / 2}
                    x2={canvasWidth - 60}
                    y2={canvasHeight / 2}
                    stroke="var(--color-border-default)"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />

                  {/* Multi-Trial Trajectory Ghost Trails — real recorded trial paths */}
                  {ghostTrialPaths.map((ghost, ghostIdx) => (
                    <polyline
                      key={`ghost-${ghostIdx}`}
                      points={ghost.points}
                      fill="none"
                      stroke={ghost.safe ? "var(--color-success-fg)" : "var(--color-danger-fg)"}
                      strokeWidth="1.5"
                      opacity="0.3"
                    />
                  ))}

                  {/* Active Path Traced so far */}
                  {tracedPoints && (
                    <polyline
                      points={tracedPoints}
                      fill="none"
                      stroke={isEmergencyStopped ? "var(--color-danger-fg)" : "var(--color-success-fg)"}
                      strokeWidth="3"
                      strokeLinecap="round"
                    />
                  )}

                  {/* Start Dock Station */}
                  <g transform={`translate(60, ${canvasHeight / 2})`}>
                    <rect x="-18" y="-18" width="36" height="36" rx="6" fill="var(--color-canvas-inset)" stroke="var(--color-accent-fg)" strokeWidth="1.5" />
                    <text x="0" y="4" fontSize="9" textAnchor="middle" fontWeight="bold" fill="var(--color-accent-fg)" fontFamily="var(--font-mono)">
                      START
                    </text>
                  </g>

                  {/* Goal Station */}
                  <g transform={`translate(${toCanvasX(24.0)}, ${canvasHeight / 2})`}>
                    <rect x="-22" y="-18" width="44" height="36" rx="6" fill="var(--color-canvas-inset)" stroke="var(--color-success-fg)" strokeWidth="1.5" />
                    <text x="0" y="4" fontSize="9" textAnchor="middle" fontWeight="bold" fill="var(--color-success-fg)" fontFamily="var(--font-mono)">
                      GOAL
                    </text>
                  </g>

                  {/* Robot LiDAR Sensor Perception Cone */}
                  {currentTelemetry && (
                    <g transform={`translate(${robotCanvasX}, ${robotCanvasY})`}>
                      <path
                        d="M 12 0 L 80 -38 A 90 90 0 0 1 80 38 Z"
                        fill={isEmergencyStopped ? "url(#lidar-cone-danger)" : "url(#lidar-cone-safe)"}
                      />

                      {/* Robot AMR Body */}
                      <rect
                        x="-14"
                        y="-11"
                        width="28"
                        height="22"
                        rx="4"
                        fill="var(--color-canvas)"
                        stroke={isEmergencyStopped ? "var(--color-danger-fg)" : isGoalReached ? "var(--color-success-fg)" : "var(--color-accent-fg)"}
                        strokeWidth="2"
                      />

                      {/* Wheels */}
                      <rect x="-10" y="-14" width="8" height="3" rx="1" fill="var(--color-fg-muted)" />
                      <rect x="2" y="-14" width="8" height="3" rx="1" fill="var(--color-fg-muted)" />
                      <rect x="-10" y="11" width="8" height="3" rx="1" fill="var(--color-fg-muted)" />
                      <rect x="2" y="11" width="8" height="3" rx="1" fill="var(--color-fg-muted)" />

                      {/* Directional Beacon / Scanner head */}
                      <circle
                        cx="5"
                        cy="0"
                        r="4"
                        fill={isEmergencyStopped ? "var(--color-danger-fg)" : "var(--color-accent-fg)"}
                        className={isEmergencyStopped ? "animate-ping" : ""}
                      />

                      {/* Forward Pointer Arrow */}
                      <path d="M 8 -4 L 14 0 L 8 4 Z" fill="var(--color-fg-default)" />
                    </g>
                  )}

                  {/* Emergency Stop Marker at the recorded halt point */}
                  {firstEmergencyStop && (
                    <g transform={`translate(${toCanvasX(firstEmergencyStop.x)}, ${toCanvasY(firstEmergencyStop.y) - 32})`}>
                      <rect x="-70" y="-12" width="140" height="24" rx="4" fill="var(--color-danger-muted)" stroke="var(--color-danger-fg)" strokeWidth="1" />
                      <text x="0" y="4" fontSize="10" textAnchor="middle" fontWeight="bold" fill="var(--color-danger-fg)" fontFamily="var(--font-sans)">
                        E-STOP at {firstEmergencyStop.x.toFixed(1)}m ({firstEmergencyStop.latency_ms}ms)
                      </text>
                    </g>
                  )}

                  {/* Goal Reached Marker if completed */}
                  {isGoalReached && currentTelemetry && (
                    <g transform={`translate(${robotCanvasX}, ${robotCanvasY - 32})`}>
                      <rect x="-60" y="-12" width="120" height="24" rx="4" fill="var(--color-success-muted)" stroke="var(--color-success-fg)" strokeWidth="1" />
                      <text x="0" y="4" fontSize="10" textAnchor="middle" fontWeight="bold" fill="var(--color-success-fg)" fontFamily="var(--font-sans)">
                        Goal reached
                      </text>
                    </g>
                  )}
                </svg>

                {/* Simulation Playback Toolbar */}
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs bg-[var(--color-canvas-subtle)] p-2.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)]">
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsPlaying(!isPlaying)}
                      disabled={!hasTrajectory}
                      className="h-8 px-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                    >
                      {isPlaying ? <PauseIcon className="h-4 w-4 mr-1 text-[var(--color-attention-fg)]" /> : <Play className="h-4 w-4 mr-1 text-[var(--color-success-fg)]" />}
                      {isPlaying ? "Pause" : "Play"}
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setPlayProgress(0.0); setIsPlaying(true); }}
                      disabled={!hasTrajectory}
                      className="h-8 px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                    >
                      <RotateCcw className="h-3.5 w-3.5 mr-1" />
                      Replay
                    </Button>

                    <div className="flex items-center gap-1 font-mono text-[11px] text-[var(--color-fg-muted)] ml-2">
                      <span>Speed:</span>
                      {[1, 2, 4].map(s => (
                        <button
                          key={s}
                          onClick={() => setPlaybackSpeed(s)}
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                            playbackSpeed === s ? "bg-[var(--color-accent-fg)] text-[var(--color-fg-on-emphasis)]" : "bg-[var(--color-canvas)] text-[var(--color-fg-muted)]"
                          }`}
                        >
                          {s}x
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Scrubber slider */}
                  <div className="flex-1 max-w-xs flex items-center gap-2">
                    <span className="font-mono text-[10px] text-[var(--color-fg-muted)]">
                      {(playProgress * 100).toFixed(0)}%
                    </span>
                    <input
                      type="range"
                      min="0"
                      max="1"
                      step="0.01"
                      value={playProgress}
                      aria-label="Simulation timeline progress"
                      disabled={!hasTrajectory}
                      onChange={(e) => {
                        setPlayProgress(parseFloat(e.target.value));
                        setIsPlaying(false);
                      }}
                      className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer disabled:opacity-50"
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1.5 text-[11px] cursor-pointer text-[var(--color-fg-muted)]">
                      <input
                        type="checkbox"
                        checked={showMultiTrials}
                        onChange={(e) => setShowMultiTrials(e.target.checked)}
                        aria-label={`Show ${trialRuns.length}-Trial Spread`}
                        disabled={trialRuns.length === 0}
                        className="rounded accent-[var(--color-accent-fg)] disabled:opacity-50"
                      />
                      <span>Show {trialRuns.length}-trial spread</span>
                    </label>
                  </div>
                </div>

                {/* Real-time Telemetry HUD Panel */}
                <PanelDivider label="Live Telemetry HUD" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-center text-xs mt-3">
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Position (X)</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {currentTelemetry ? `${currentTelemetry.x.toFixed(1)} m / 24.0 m` : "—"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Robot Speed</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {currentTelemetry && currentTelemetry.v !== undefined ? `${currentTelemetry.v.toFixed(2)} m/s` : "—"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Perception Latency</span>
                    <div
                      className={`font-mono font-bold ${
                        currentTelemetry === null
                          ? "text-[var(--color-fg-muted)]"
                          : freshnessBudget !== null && currentTelemetry.latency_ms > freshnessBudget
                            ? "text-[var(--color-danger-fg)]"
                            : "text-[var(--color-success-fg)]"
                      }`}
                    >
                      {currentTelemetry
                        ? `${currentTelemetry.latency_ms} ms${freshnessBudget !== null ? ` (Limit: ${freshnessBudget}ms)` : ""}`
                        : "—"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Safety Interlock</span>
                    <div
                      className={`font-mono font-bold ${
                        currentTelemetry === null
                          ? "text-[var(--color-fg-muted)]"
                          : isEmergencyStopped
                            ? "text-[var(--color-danger-fg)]"
                            : "text-[var(--color-success-fg)]"
                      }`}
                    >
                      {currentTelemetry
                        ? isEmergencyStopped
                          ? "E-STOP ENGAGED"
                          : isGoalReached
                            ? "GOAL NOMINAL"
                            : currentTelemetry.status
                        : "—"}
                    </div>
                  </Panel>
                </div>

                {/* Latency component breakdown — averaged over the recorded twin path */}
                <PanelDivider label="Latency Component Breakdown (twin path average)" />
                <div className="grid grid-cols-3 gap-2 text-center text-xs mt-3">
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Batch Wait</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {latencyBreakdown.batchWaitMs !== null ? `${latencyBreakdown.batchWaitMs}ms` : "—"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">GPU Compute</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {latencyBreakdown.gpuMs !== null ? `${latencyBreakdown.gpuMs}ms` : "—"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Network Delay</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {latencyBreakdown.networkMs !== null ? `${latencyBreakdown.networkMs}ms` : "—"}
                    </div>
                  </Panel>
                </div>
              </div>

              {/* Interactive Parameter Tuning (Engineer Mode) */}
              <Panel variant="inset" padding="md" className="border border-[var(--color-border-default)]">
                <PanelHeader
                  title="Interactive Digital Twin Parameter Tuning (Engineer Mode)"
                  subtitle="Sweep live inference batching, transport queues, and clock sync through the backend twin"
                  divider={true}
                />
                <div className="grid gap-4 md:grid-cols-3 pt-2">
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-[var(--color-fg-default)]">Batching Window:</span>
                      <span className="font-mono font-bold text-[var(--color-accent-fg)]">{customBatchWindow} ms</span>
                    </div>
                    <input
                      type="range"
                      min="50"
                      max="250"
                      step="10"
                      value={customBatchWindow}
                      aria-label="Batching Window"
                      onChange={(e) => setCustomBatchWindow(Number(e.target.value))}
                      className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer"
                    />
                    <span className="text-[10px] text-[var(--color-fg-muted)]">Twin parameter: dynamic batching window</span>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-[var(--color-fg-default)]">ROS 2 QoS Queue Depth:</span>
                      <span className="font-mono font-bold text-[var(--color-accent-fg)]">{customQosDepth} msgs</span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="10"
                      step="1"
                      value={customQosDepth}
                      aria-label="ROS 2 QoS Queue Depth"
                      onChange={(e) => setCustomQosDepth(Number(e.target.value))}
                      className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer"
                    />
                    <span className="text-[10px] text-[var(--color-fg-muted)]">Twin parameter: ROS 2 QoS depth (buffers above 5)</span>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="font-medium text-[var(--color-fg-default)]">Clock Skew:</span>
                      <span className="font-mono font-bold text-[var(--color-accent-fg)]">{customClockSkew} ms</span>
                    </div>
                    <input
                      type="range"
                      min="0"
                      max="50"
                      step="5"
                      value={customClockSkew}
                      aria-label="Clock Skew"
                      onChange={(e) => setCustomClockSkew(Number(e.target.value))}
                      className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer"
                    />
                    <span className="text-[10px] text-[var(--color-fg-muted)]">Twin parameter: injected clock skew</span>
                  </div>
                </div>

                <div className="mt-4 flex items-center justify-end">
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleRunCustomSimulation}
                    disabled={simulating}
                    className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    {simulating ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Zap className="h-4 w-4 mr-1.5" />}
                    Simulate Custom Parameters
                  </Button>
                </div>
              </Panel>
            </PanelSection>
          </Panel>
        </PanelStack>

        {/* Right: Intervention & Artifact Details */}
        <PanelStack space="lg">
          <Panel padding="none">
            <PanelHeader
              title="Intervention Specification"
              subtitle="Counterfactual intervention applied to the selected branch"
              divider={true}
            />
            <PanelSection dividerBefore={false} className="space-y-4">
              <div>
                <span className="text-xs text-[var(--color-fg-muted)] block uppercase font-semibold">Intervention Code:</span>
                <div className="mt-1 p-3 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-accent-muted)]/20 text-xs font-mono text-[var(--color-accent-fg)] break-words">
                  {currentExp?.intervention || "No intervention recorded for this branch"}
                </div>
              </div>

              <PanelDivider label="Branch Configuration" />

              <div className="space-y-2">
                <KV label="Branch Target" value={currentExp?.branch_name || currentExp?.experiment_id || "—"} />
                <KV label="Digital Twin Engine" value="Pure Python Simulation" />
                <KV label="Reproduction Trials" value={trialCount ? `${trialCount} runs (seeded)` : "—"} />
                <KV label="Freshness Budget" value={freshnessBudget !== null ? `${freshnessBudget} ms` : "—"} />
                <KV label="Control Deadline" value={controlDeadline !== null ? `${controlDeadline} ms` : "—"} />
                <KV label="Baseline Failure Rate" value={oracle.baseline_comparison !== undefined ? `${Math.round(oracle.baseline_comparison * 100)}%` : "—"} />
              </div>

              <PanelDivider label="Trial Summary" />

              <div className="space-y-2">
                <KV label="Average Latency" value={avgLatency !== null ? `${avgLatency} ms` : "—"} />
                <KV label="p99 Latency" value={p99Latency !== null ? `${p99Latency} ms` : "—"} />
                <KV label="Max Latency" value={maxLatency !== null ? `${maxLatency} ms` : "—"} />
                <KV
                  label="Emergency Stops"
                  value={
                    trialVerdict
                      ? `${trialVerdict.haltedTrialCount}/${trialRuns.length} trials`
                      : "—"
                  }
                />
              </div>

              {trialVerdict?.haltReason && (
                <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--color-danger-muted)]/30 border border-[var(--color-danger-muted)] text-xs text-[var(--color-danger-fg)]">
                  <span className="font-semibold block mb-1">Halt reason (from twin)</span>
                  {trialVerdict.haltReason}
                </div>
              )}

              {currentExp?.conclusion && (
                <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-xs text-[var(--color-fg-default)]">
                  <span className="font-semibold block mb-1">Conclusion (from pipeline)</span>
                  {currentExp.conclusion}
                </div>
              )}

              <PanelDivider label="Candidate Artifacts" />

              {recordedArtifacts.length > 0 ? (
                <div className="space-y-2">
                  {recordedArtifacts.map((art) => (
                    <div
                      key={art.path}
                      onClick={() => handleOpenArtifactInspector(art)}
                      className="p-2.5 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] hover:border-[var(--color-border-strong)] transition-colors cursor-pointer flex items-center justify-between text-xs gap-2"
                    >
                      <div className="min-w-0">
                        <span className="font-mono text-[var(--color-fg-default)] block font-semibold truncate">{art.name}</span>
                        <span className="text-[10px] text-[var(--color-fg-muted)] break-all">{art.path}</span>
                      </div>
                      <Badge tone="neutral" size="sm">{art.type}</Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-[var(--color-fg-muted)]">
                  {noData
                    ? "Select a branch to see the artifacts its simulation produced."
                    : "This branch recorded no artifacts."}
                </p>
              )}
            </PanelSection>
          </Panel>
        </PanelStack>
      </PanelStack>
    </div>
  );
}
