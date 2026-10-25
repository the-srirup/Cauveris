"use client";

import { useState, useEffect, useMemo, useRef, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import {
  Button,
  Card,
  Stat,
  Badge,
  KV,
  PageHeader,
  Panel,
  PanelSection,
  PanelStack,
  PanelHeader,
  PanelFooter,
  PanelCard,
  PanelDivider,
  Slider,
} from "@/components/ui";
import { api, EvidenceItem, Experiment, IncidentSystemModel, TrajectoryPoint } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { readDeepLink } from "@/holographic";
import {
  Check,
  Download,
  Play,
  RotateCcw,
  FlaskConical,
  ArrowLeft,
  Loader2,
  Sliders,
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
  const [systemModel, setSystemModel] = useState<IncidentSystemModel | null>(null);
  const [evidenceItems, setEvidenceItems] = useState<EvidenceItem[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [selectedBranch, setSelectedBranch] = useState<string>("");

  // Trajectory Simulation Animation State
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [playProgress, setPlayProgress] = useState<number>(0.0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const [showMultiTrials, setShowMultiTrials] = useState<boolean>(true);
  const animationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

  // Engineer Mode Custom Interactive Parameters
  const [customBatchWindow, setCustomBatchWindow] = useState<number>(100);
  const [customQosDepth, setCustomQosDepth] = useState<number>(1);
  const [customClockSkew, setCustomClockSkew] = useState<number>(0);
  const [customSimResult, setCustomSimResult] = useState<any>(null);

  const loadExperiments = async (id: string) => {
    setDataLoading(true);
    try {
      const res = await api.getExperiments(id);
      setExperiments(res?.experiments ?? []);
    } catch (e: any) {
      setExperiments([]);
      setError(e?.message || "Could not load the experiment branches for this incident");
    } finally {
      setDataLoading(false);
    }
  };

  const loadSystemModel = async (id: string) => {
    try {
      const model = await api.getSystemModel(id);
      setSystemModel(model);
    } catch {
      // The model is an addition to what is shown, not a prerequisite: the
      // experiments carry their own numbers.  Its absence is not an error.
      setSystemModel(null);
    }
  };

  const loadEvidence = async (id: string) => {
    try {
      const incident = await api.get(id);
      setEvidenceItems(incident?.evidence_items ?? []);
    } catch {
      setEvidenceItems([]);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadExperiments(incidentId);
      loadSystemModel(incidentId);
      loadEvidence(incidentId);
    } else {
      setExperiments([]);
      setSystemModel(null);
      setEvidenceItems([]);
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

  const activeExperiments = experiments;

  const selectedExp = activeExperiments.find(
    (e) => (e.experiment_id || e.id) === selectedBranch
  ) || activeExperiments[0] || null;

  // Keep the selection pointing at a branch that exists.
  useEffect(() => {
    if (activeExperiments.length === 0) {
      setSelectedBranch("");
      return;
    }
    if (!activeExperiments.some((e) => (e.experiment_id || e.id) === selectedBranch)) {
      setSelectedBranch(activeExperiments[0].experiment_id || activeExperiments[0].id);
    }
  }, [activeExperiments, selectedBranch]);

  const currentExp = selectedExp;

  /**
   * The paths of every trial the twin actually ran.
   *
   * The backend returns one entry per trial, each holding its own path and
   * its own outcome, so the spread on the canvas is the spread that was
   * measured - not a picture of one.
   */
  const trials: any[] = useMemo(
    () => customSimResult?.trajectories ?? currentExp?.trajectories ?? [],
    [currentExp, customSimResult]
  );

  const trialPaths: TrajectoryPoint[][] = useMemo(
    () =>
      trials
        .map((trial) => (Array.isArray(trial) ? trial : trial?.path ?? []))
        .filter((path): path is TrajectoryPoint[] => Array.isArray(path) && path.length > 0),
    [trials]
  );

  const trajectoryPoints: TrajectoryPoint[] = useMemo(() => {
    if (customSimResult?.trajectory?.length > 0) return customSimResult.trajectory;
    const experimentPath = currentExp?.trajectory;
    if (experimentPath && experimentPath.length > 0) return experimentPath;
    if (trialPaths.length > 0) return trialPaths[0];
    return [];
  }, [currentExp, customSimResult, trialPaths]);

  /**
   * Every number the panel shows comes from the run that produced it.
   *
   * An experiment carries its own oracle (the mean latency, the budget, the
   * emergency-stop count); the custom simulation carries the same numbers
   * flat.  Nothing here is a constant.
   */
  const outcome = useMemo(() => {
    const oracle = currentExp?.failure_oracle ?? null;
    if (customSimResult) {
      return {
        trials: customSimResult.trial_count ?? null,
        emergencyStops: customSimResult.reproduction_count ?? null,
        collisions: null as number | null,
        avgLatencyMs: customSimResult.avg_latency_ms ?? null,
        p95LatencyMs: customSimResult.p99_latency_ms ?? null,
        budgetMs:
          customSimResult.freshness_budget_ms ??
          systemModel?.budget?.freshness_budget_ms ??
          null,
        baselineLatencyMs: null as number | null,
        supported: customSimResult.hypothesis_supported ?? null,
        budgetSatisfied:
          customSimResult.hypothesis_supported === undefined
            ? null
            : Boolean(customSimResult.hypothesis_supported),
      };
    }
    const robot = oracle?.robot_outcome ?? null;
    return {
      trials: robot?.trials ?? null,
      emergencyStops: robot?.emergency_stops ?? null,
      collisions: robot?.collisions ?? null,
      avgLatencyMs: oracle?.avg_total_latency ?? null,
      p95LatencyMs: oracle?.p95_total_latency ?? null,
      budgetMs:
        oracle?.freshness_budget_ms ?? systemModel?.budget?.freshness_budget_ms ?? null,
      baselineLatencyMs: oracle?.baseline?.mean_age_ms ?? null,
      supported: oracle?.hypothesis_supported ?? null,
      budgetSatisfied:
        oracle?.budget_satisfied === undefined ? null : Boolean(oracle.budget_satisfied),
    };
  }, [currentExp, customSimResult, systemModel]);

  const isConfirmed = outcome.emergencyStops === 0 && (currentExp?.reproduction_rate ?? 1) === 0;

  // The arena is the route the twin was given: the waypoint it was asked to
  // reach, not where a run happened to stop.
  const arena = useMemo(() => {
    const allPoints = trialPaths.length > 0 ? trialPaths.flat() : trajectoryPoints;
    const targets = trials
      .map((trial) => trial?.target)
      .filter((target): target is { x: number; y: number } => Boolean(target));
    const goalX = targets.length
      ? Math.max(...targets.map((t) => t.x))
      : allPoints.length
        ? Math.max(...allPoints.map((p) => p.x))
        : 0;
    const maxY =
      targets.length && allPoints.length
        ? Math.max(
            ...targets.map((t) => Math.abs(t.y)),
            ...allPoints.map((p) => Math.abs(p.y))
          )
        : allPoints.length
          ? Math.max(...allPoints.map((p) => Math.abs(p.y)))
          : 0;
    return { lengthM: goalX, widthM: maxY * 2, goalX, maxY };
  }, [trialPaths, trajectoryPoints, trials]);

  // Current interpolated point along trajectory based on playProgress
  const currentPointIndex = trajectoryPoints.length
    ? Math.min(
        Math.floor(playProgress * (trajectoryPoints.length - 1)),
        trajectoryPoints.length - 1
      )
    : -1;
  const currentTelemetry: TrajectoryPoint | null =
    currentPointIndex >= 0 ? trajectoryPoints[currentPointIndex] ?? null : null;

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
    setSimulating(true);
    setError(null);
    try {
      notify("Executing digital twin counterfactual simulations across all branches...", "info");
      const res = await api.runExperiment(incidentId);
      if (res && res.experiments) {
        setExperiments(res.experiments);
      }
      notify("Digital twin simulation completed! 20 trials evaluated per branch.", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Simulation failed", "error");
    } finally {
      setSimulating(false);
    }
  };

  const handleRunCustomSimulation = async () => {
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

      if (res.hypothesis_supported) {
        notify(`✓ Custom parameters safe: 0% emergency stops (Avg latency ${res.avg_latency_ms}ms <= ${res.freshness_budget_ms}ms).`, "success");
      } else {
        notify(`✕ Safety budget exceeded: ${res.reproduction_count}/20 emergency stops triggered.`, "info");
      }
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Custom simulation failed", "error");
    } finally {
      setSimulating(false);
    }
  };

  const handleOpenExperimentInspector = (exp: Experiment) => {
    const expData: InspectorData = {
      mode: "experiment",
      experimentId: exp.experiment_id || exp.id,
      experimentData: {
        ...exp,
        type: "Digital Twin Simulation",
        confidence: exp.reproduction_rate !== undefined ? Math.round((1 - exp.reproduction_rate) * 100) : undefined,
        limitations: exp.status === "SUCCESS"
          ? ["Limited to simulated environment", "Assumes accurate physics model"]
          : ["Emergency stop triggered", "Reproduction rate 100%"],
      },
    };
    openInspector("experiment", expData);
  };

  const handleOpenArtifactInspector = (path: string) => {
    // The inspector is given the bundle's own record of the file: its
    // checksum, its size, its validation status.  Nothing here is invented.
    const item = evidenceItems.find(
      (ev) => ev.file_path === path || ev.file_path.endsWith(path)
    );
    const data: InspectorData = {
      mode: "evidence",
      evidenceId: item?.file_path ?? path,
      evidenceData: {
        name: path.split("/").pop() ?? path,
        type: item?.file_type ?? (path.endsWith(".py") ? "Source Code" : "Config"),
        path: item?.file_path ?? path,
        checksum: item?.checksum_sha256,
        size_bytes: item?.size_bytes,
        status: item?.status,
        is_required: item?.is_required,
        validation_errors: item?.validation_errors,
        ingested_at: undefined,
      },
    };
    openInspector("evidence", data);
  };

  const handleExportData = async () => {
    setLoading(true);
    setError(null);
    try {
      const expData = {
        incident_id: incidentId,
        experiments: activeExperiments,
        active_branch: selectedBranch,
        exported_at: new Date().toISOString(),
        active_trajectory: trajectoryPoints,
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

  // Canvas coordinates
  const canvasWidth = 740;
  const canvasHeight = 220;
  const mapMaxX = arena.lengthM > 0 ? arena.lengthM * 1.05 : 1;
  const robotCanvasX = 60 + ((currentTelemetry?.x ?? 0) / mapMaxX) * (canvasWidth - 140);
  const robotCanvasY = canvasHeight / 2 + (currentTelemetry?.y ?? 0) * 30;
  const isEmergencyStopped = currentTelemetry?.emergency_stop ?? false;
  const isGoalReached = currentTelemetry?.status === "GOAL_REACHED";
  const freshnessLimitMs = outcome.budgetMs;

  /** The files the intervention names, taken from the intervention text. */
  const interventionFiles = useMemo(() => {
    const text = currentExp?.intervention ?? "";
    const matches = text.match(/[\w./-]+\.(?:ya?ml|py|json|toml|cfg|ini|xml|txt)/g);
    return Array.from(new Set(matches ?? []));
  }, [currentExp]);

  /**
   * The incident's own parameter values, and where each of them came from.
   *
   * A value the bundle declared and a value the model defaulted to are both
   * shown, and the difference is visible: a default is not evidence.
   */
  const baselineParameter = (name: string): number | null => {
    const value = systemModel?.parameters?.[name];
    return typeof value === "number" ? value : null;
  };

  const parameterProvenance = (name: string): string => {
    if (!systemModel) return "unknown - no calibrated model";
    if (systemModel.parameters_from_evidence?.[name]) {
      return `declared in ${systemModel.parameter_sources?.[name] ?? "the bundle"}`;
    }
    return "model default - not evidence";
  };

  // The sliders start from the incident's own values, so the first custom run
  // is the baseline and every move away from it is the change being tested.
  useEffect(() => {
    if (!systemModel) return;
    const params = systemModel.parameters ?? {};
    if (typeof params.batching_window_ms === "number") {
      setCustomBatchWindow(params.batching_window_ms);
    }
    if (typeof params.qos_queue_depth === "number") {
      setCustomQosDepth(params.qos_queue_depth);
    }
    if (typeof params.clock_skew_ms === "number") {
      setCustomClockSkew(params.clock_skew_ms);
    }
  }, [systemModel]);

  return (
    <div className="w-full space-y-5">
      <PageHeader
        title="Ghost Lab"
        subtitle="Controlled experiment execution and counterfactual reality branch analysis"
        badge={
          activeExperiments.length === 0 ? (
            <Badge tone="secondary" dot={true}>
              No Branches Yet
            </Badge>
          ) : (
            <Badge tone={isConfirmed ? "success" : "secondary"} dot={true}>
              {isConfirmed ? "Root Cause Fix Discovered" : "Branch Active"}
            </Badge>
          )
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
          {currentExp ? (
            <Badge tone={isConfirmed ? "success" : "danger"}>
              {isConfirmed
                ? "0% Failure Rate"
                : `${Math.round((currentExp?.reproduction_rate ?? 1.0) * 100)}% Failure Rate`}
            </Badge>
          ) : (
            <Badge tone="neutral">No Branch Selected</Badge>
          )}
        </div>
      </div>

      {/* Branch Selector Tabs */}
      <Panel variant="inset" padding="none">
        <PanelHeader title="Experiment Branches" subtitle="Select a counterfactual branch to inspect" divider={true} />
        <PanelSection dividerBefore={false}>
          {activeExperiments.length === 0 ? (
            <div className="flex flex-col gap-3 py-2">
              <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                {dataLoading
                  ? "Loading the branches this incident produced..."
                  : "This incident has no experiment branches yet. They are produced by running the digital twin against the incident's hypotheses - each branch is one counterfactual, simulated against the calibrated model of this incident."}
              </p>
              {!dataLoading && (
                <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                  Use <span className="font-semibold text-[var(--color-fg-default)]">Run Twin Simulations</span>{" "}
                  above to produce them.
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              {activeExperiments.map((exp) => {
                const expKey = exp.experiment_id || exp.id;
                const isSelected = selectedBranch === expKey;
                const expConfirmed = (exp.reproduction_rate ?? 1.0) === 0.0;

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
                      ({Math.round((exp.reproduction_rate ?? 1.0) * 100)}% fail)
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </PanelSection>
      </Panel>

      <PanelStack space="lg" className="grid gap-[var(--section-gap)] lg:grid-cols-[2fr_1fr]">
        {/* Left: Experiment Control & Trajectories */}
        <PanelStack space="lg">
          <Panel padding="none">
            <PanelHeader
              title={`Active Branch: ${currentExp?.name || selectedBranch || "No Experiments"}`}
              subtitle={`${activeExperiments.length} experiment branches available`}
              divider={true}
            />
            <PanelSection dividerBefore={false} className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <Stat
                label="Trials Executed"
                value={outcome.trials !== null ? String(outcome.trials) : "-"}
                sub="Seeded digital-twin trials"
                trend="flat"
              />
              <Stat
                label="Reproduction Rate"
                value={
                  currentExp
                    ? `${Math.round((currentExp.reproduction_rate ?? 1.0) * 100)}%`
                    : "-"
                }
                sub={
                  outcome.emergencyStops !== null
                    ? `${outcome.emergencyStops}/${outcome.trials ?? "?"} emergency stops`
                    : "No run yet"
                }
                trend={isConfirmed ? "success" : currentExp ? "danger" : "muted"}
              />
              <Stat
                label="Perception Latency (mean)"
                value={outcome.avgLatencyMs !== null ? `${outcome.avgLatencyMs}ms` : "-"}
                sub={
                  outcome.budgetMs !== null
                    ? outcome.avgLatencyMs !== null && outcome.avgLatencyMs > outcome.budgetMs
                      ? `Over the ${outcome.budgetMs}ms freshness budget`
                      : `Inside the ${outcome.budgetMs}ms freshness budget`
                    : "Budget unknown"
                }
                trend={
                  outcome.avgLatencyMs === null || outcome.budgetMs === null
                    ? "muted"
                    : outcome.avgLatencyMs <= outcome.budgetMs
                      ? "success"
                      : "danger"
                }
              />
              <Stat
                label="Safety Outcome"
                value={
                  outcome.emergencyStops === null
                    ? "-"
                    : outcome.emergencyStops === 0
                      ? "CLEAR"
                      : "TRIPPED"
                }
                sub={
                  outcome.collisions !== null && outcome.collisions > 0
                    ? `${outcome.collisions} collision(s)`
                    : isConfirmed
                      ? "No emergency stop across the trials"
                      : "Emergency stop(s) in the trials"
                }
                trend={
                  outcome.emergencyStops === null
                    ? "muted"
                    : outcome.emergencyStops === 0
                      ? "success"
                      : "danger"
                }
              />
            </PanelSection>
          </Panel>

          {/* Real 2D Robot Trajectory Simulation Canvas */}
          <Panel padding="none">
            <PanelHeader
              title="Parallel Robot Trajectory Counterfactual Simulation"
              subtitle={
                trialPaths.length > 0
                  ? `${trialPaths.length} simulated runs • ${trialPaths[0].length} samples each • semi-implicit Euler integration with the ISO 13849 Category 1 watchdog`
                  : "No trajectory has been produced for this branch yet"
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
                    {arena.lengthM > 0
                      ? `Route: ${arena.lengthM.toFixed(1)} m to the waypoint`
                      : "Route: not simulated"}
                  </span>
                  {outcome.emergencyStops === null ? (
                    <Badge tone="neutral">No Run Yet</Badge>
                  ) : outcome.emergencyStops === 0 ? (
                    <Badge tone="success">
                      {outcome.trials ?? 0}/{outcome.trials ?? 0} runs reached the waypoint
                    </Badge>
                  ) : (
                    <Badge tone="danger">
                      {outcome.emergencyStops}/{outcome.trials ?? "?"} runs stopped for stale perception
                    </Badge>
                  )}
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

                  {/* Distance scale along the route - every tick is a real metre */}
                  {arena.lengthM > 0 &&
                    Array.from({ length: 5 }, (_, i) => {
                      const metres = (arena.lengthM / 4) * i;
                      const x = 60 + (metres / mapMaxX) * (canvasWidth - 140);
                      return (
                        <g key={`tick-${i}`}>
                          <line
                            x1={x}
                            y1={canvasHeight / 2 - 8}
                            x2={x}
                            y2={canvasHeight / 2 + 8}
                            stroke="var(--color-border-muted)"
                            strokeWidth="1"
                          />
                          <text
                            x={x}
                            y={canvasHeight / 2 + 22}
                            fontSize="8"
                            textAnchor="middle"
                            fill="var(--color-fg-muted)"
                            fontFamily="var(--font-mono)"
                          >
                            {metres.toFixed(1)}m
                          </text>
                        </g>
                      );
                    })}

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

                  {/* Every other run of this branch, drawn as the spread behind the active one */}
                  {showMultiTrials && trialPaths.length > 1 && (
                    <g opacity="0.35">
                      {trialPaths.map((path, trialIdx) => {
                        if (trialIdx === 0) return null;
                        const stopped = path.some((p) => p.emergency_stop);
                        const points = path
                          .map(
                            (p, i) =>
                              `${60 + (p.x / mapMaxX) * (canvasWidth - 140)},${
                                canvasHeight / 2 + p.y * 30
                              }${i === path.length - 1 ? "" : " "}`
                          )
                          .join(" ");
                        return (
                          <polyline
                            key={`run-${trialIdx}`}
                            points={points}
                            fill="none"
                            stroke={
                              stopped
                                ? "var(--color-danger-fg)"
                                : "var(--color-success-fg)"
                            }
                            strokeWidth="1.2"
                          />
                        );
                      })}
                    </g>
                  )}

                  {/* Active Path Traced so far */}
                  {currentTelemetry && (
                    <line
                      x1="60"
                      y1={canvasHeight / 2}
                      x2={robotCanvasX}
                      y2={robotCanvasY}
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

                  {/* The waypoint the twin was asked to reach */}
                  {arena.lengthM > 0 && (
                    <g
                      transform={`translate(${
                        60 + (arena.goalX / mapMaxX) * (canvasWidth - 140)
                      }, ${canvasHeight / 2})`}
                    >
                      <rect x="-22" y="-18" width="44" height="36" rx="6" fill="var(--color-canvas-inset)" stroke="var(--color-success-fg)" strokeWidth="1.5" />
                      <text x="0" y="4" fontSize="9" textAnchor="middle" fontWeight="bold" fill="var(--color-success-fg)" fontFamily="var(--font-mono)">
                        GOAL
                      </text>
                    </g>
                  )}

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

                  {/* Emergency Stop Marker if halted */}
                  {isEmergencyStopped && (
                    <g transform={`translate(${robotCanvasX}, ${robotCanvasY - 32})`}>
                      <rect x="-65" y="-12" width="130" height="24" rx="4" fill="var(--color-danger-muted)" stroke="var(--color-danger-fg)" strokeWidth="1" />
                      <text x="0" y="4" fontSize="10" textAnchor="middle" fontWeight="bold" fill="var(--color-danger-fg)" fontFamily="var(--font-sans)">
                        ⚠ E-STOP: Stale Perception
                      </text>
                    </g>
                  )}

                  {/* Goal Reached Marker if completed */}
                  {isGoalReached && (
                    <g transform={`translate(${robotCanvasX}, ${robotCanvasY - 32})`}>
                      <rect x="-60" y="-12" width="120" height="24" rx="4" fill="var(--color-success-muted)" stroke="var(--color-success-fg)" strokeWidth="1" />
                      <text x="0" y="4" fontSize="10" textAnchor="middle" fontWeight="bold" fill="var(--color-success-fg)" fontFamily="var(--font-sans)">
                        ✓ Navigation Nominal
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
                      className="h-8 px-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                    >
                      {isPlaying ? <PauseIcon className="h-4 w-4 mr-1 text-[var(--color-attention-fg)]" /> : <Play className="h-4 w-4 mr-1 text-[var(--color-success-fg)]" />}
                      {isPlaying ? "Pause" : "Play"}
                    </Button>

                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => { setPlayProgress(0.0); setIsPlaying(true); }}
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
                      onChange={(e) => {
                        setPlayProgress(parseFloat(e.target.value));
                        setIsPlaying(false);
                      }}
                      className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer"
                    />
                  </div>

                  <div className="flex items-center gap-3">
                    <label className="flex items-center gap-1.5 text-[11px] cursor-pointer text-[var(--color-fg-muted)]">
                      <input
                        type="checkbox"
                        checked={showMultiTrials}
                        onChange={(e) => setShowMultiTrials(e.target.checked)}
                        aria-label="Show the spread of all runs"
                        className="rounded accent-[var(--color-accent-fg)]"
                      />
                      <span>
                        {trialPaths.length > 0
                          ? `Show all ${trialPaths.length} runs`
                          : "Show all runs"}
                      </span>
                    </label>
                  </div>
                </div>

                {/* Real-time Telemetry HUD Panel */}
                <PanelDivider label="Live Telemetry HUD" />
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 text-center text-xs mt-3">
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Position (X)</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {currentTelemetry
                        ? `${currentTelemetry.x.toFixed(1)} m${
                            arena.lengthM > 0 ? ` / ${arena.lengthM.toFixed(1)} m` : ""
                          }`
                        : "-"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Robot Speed</span>
                    <div className="font-mono text-[var(--color-fg-default)] font-bold">
                      {currentTelemetry ? `${currentTelemetry.v.toFixed(2)} m/s` : "-"}
                    </div>
                  </Panel>
                  <Panel variant="inset" padding="sm">
                    <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Perception Latency</span>
                    <div
                      className={`font-mono font-bold ${
                        currentTelemetry === null
                          ? "text-[var(--color-fg-muted)]"
                          : freshnessLimitMs !== null &&
                              currentTelemetry.latency_ms > freshnessLimitMs
                            ? "text-[var(--color-danger-fg)]"
                            : "text-[var(--color-success-fg)]"
                      }`}
                    >
                      {currentTelemetry
                        ? `${currentTelemetry.latency_ms} ms${
                            freshnessLimitMs !== null
                              ? ` (Limit: ${freshnessLimitMs}ms)`
                              : ""
                          }`
                        : "-"}
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
                      {!currentTelemetry
                        ? "NO DATA"
                        : isEmergencyStopped
                          ? "E-STOP ENGAGED"
                          : isGoalReached
                            ? "GOAL NOMINAL"
                            : "TRACKING"}
                    </div>
                  </Panel>
                </div>
              </div>

              {/* Interactive Parameter Tuning (Engineer Mode) */}
              <Panel variant="inset" padding="md" className="border border-[var(--color-border-default)]">
                <PanelHeader
                  title="Interactive Digital Twin Parameter Tuning (Engineer Mode)"
                  subtitle="Tweak live inference batching, transport queues, and clock sync to test boundaries"
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
                    <span className="text-[10px] text-[var(--color-fg-muted)]">
                      Incident value:{" "}
                      {baselineParameter("batching_window_ms") !== null
                        ? `${baselineParameter("batching_window_ms")} ms`
                        : "unknown"}{" "}
                      • {parameterProvenance("batching_window_ms")}
                    </span>
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
                    <span className="text-[10px] text-[var(--color-fg-muted)]">
                      Incident value:{" "}
                      {baselineParameter("qos_queue_depth") !== null
                        ? `${baselineParameter("qos_queue_depth")} msgs`
                        : "unknown"}{" "}
                      • {parameterProvenance("qos_queue_depth")}
                    </span>
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
                    <span className="text-[10px] text-[var(--color-fg-muted)]">
                      Incident value:{" "}
                      {baselineParameter("clock_skew_ms") !== null
                        ? `${baselineParameter("clock_skew_ms")} ms`
                        : "unknown"}{" "}
                      • {parameterProvenance("clock_skew_ms")}
                    </span>
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
                <div className="mt-1 p-3 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-accent-muted)]/20 text-xs font-mono text-[var(--color-accent-fg)]">
                  {currentExp?.intervention ?? "No intervention selected"}
                </div>
              </div>

              <PanelDivider label="Branch Configuration" />

              <div className="space-y-2">
                <KV label="Branch Target" value={currentExp?.branch_name || selectedBranch || "N/A"} />
                <KV label="Digital Twin Engine" value="CloudToRobotDigitalTwin (Python)" />
                <KV
                  label="Reproduction Trials"
                  value={outcome.trials !== null ? `${outcome.trials} seeded runs` : "not run"}
                />
                <KV
                  label="Target Freshness"
                  value={
                    outcome.budgetMs !== null
                      ? `${outcome.budgetMs}ms threshold`
                      : "not declared"
                  }
                />
                <KV
                  label="Model Status"
                  value={
                    systemModel
                      ? systemModel.model_status === "fitted"
                        ? "fitted to this incident"
                        : systemModel.model_status === "declared-configuration-only"
                          ? "declared configuration only - not fitted"
                          : "uncalibrated"
                      : "not loaded"
                  }
                />
              </div>

              <PanelDivider label="Files Named by the Intervention" />

              <div className="space-y-2">
                {interventionFiles.length === 0 ? (
                  <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
                    {currentExp
                      ? "This intervention does not name a file in the bundle - it changes the deployment rather than a file."
                      : "No branch is selected."}
                  </p>
                ) : (
                  interventionFiles.map((path) => {
                    const item = evidenceItems.find(
                      (ev) => ev.file_path === path || ev.file_path.endsWith(path)
                    );
                    return (
                      <div
                        key={path}
                        onClick={() => handleOpenArtifactInspector(path)}
                        className="p-2.5 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] hover:border-[var(--color-border-strong)] transition-colors cursor-pointer flex items-center justify-between text-xs"
                      >
                        <div className="min-w-0">
                          <span className="font-mono text-[var(--color-fg-default)] block font-semibold truncate">
                            {path.split("/").pop() ?? path}
                          </span>
                          <span className="text-[10px] text-[var(--color-fg-muted)] break-all">
                            {item ? item.file_path : `${path} (not in this bundle)`}
                          </span>
                        </div>
                        <Badge tone="neutral" size="sm">
                          {item?.file_type ?? "not in bundle"}
                        </Badge>
                      </div>
                    );
                  })
                )}
              </div>
            </PanelSection>
          </Panel>
        </PanelStack>
      </PanelStack>
    </div>
  );
}
