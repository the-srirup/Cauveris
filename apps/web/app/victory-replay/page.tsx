"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import {
  Button,
  Badge,
  KV,
  PageHeader,
  Panel,
  PanelSection,
  PanelStack,
  PanelDivider,
  EmptyState,
  EmptyStateIcons,
  Stat,
} from "@/components/ui";
import { api, ApplyPatchResult, ReplaySide, VictoryReplayResponse } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { Check, RotateCcw, Download, Play, AlertTriangle, ShieldCheck, Loader2 } from "lucide-react";

function PauseIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="6" y="4" width="4" height="16" />
      <rect x="14" y="4" width="4" height="16" />
    </svg>
  );
}

export default function VictoryReplay() {
  return (
    <AuthGate redirect="/victory-replay" loadingLabel="Loading Victory Replay...">
      <VictoryReplayContent />
    </AuthGate>
  );
}

/** Pull the path point at a normalized progress position out of a real trajectory. */
function pointAt(progress: number, side: ReplaySide | null) {
  const path = side?.trajectory ?? [];
  if (!path.length) return null;
  const idx = Math.min(
    Math.floor(progress * (path.length - 1)),
    path.length - 1
  );
  return path[Math.max(idx, 0)];
}

function VictoryReplayContent() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, setIncidentContext } = useShell();

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Victory Replay",
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
  const [error, setError] = useState<string | null>(null);
  const [rollbackStatus, setRollbackStatus] = useState<string | null>(null);
  const [replayData, setReplayData] = useState<VictoryReplayResponse | null>(null);
  const [replayLoaded, setReplayLoaded] = useState(false);

  // Synchronized Replay Scrubbing & Animation
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [progress, setProgress] = useState<number>(0.0);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);
  const animationFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number | null>(null);

  // Load the real before/after twin comparison from the backend.
  const loadReplay = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getVictoryReplay(id);
      setReplayData(res);
    } catch (e: any) {
      setError(e?.message || "Failed to load the victory replay comparison");
    } finally {
      setReplayLoaded(true);
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!incidentId) return;
    loadReplay(incidentId);
  }, [incidentId]);

  // Synchronized animation loop
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
        setProgress((prev) => {
          const next = prev + (delta * 0.14 * playbackSpeed);
          if (next >= 1.0) {
            return 0.0;
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

  const before = replayData?.before ?? null;
  const after = replayData?.after ?? null;
  const delta = replayData?.delta ?? null;
  const budget = replayData?.freshness_budget_ms ?? 120;
  const patch = replayData?.patch ?? null;
  const hasComparison = Boolean(before && after);

  // Live telemetry read off the twin's real recorded path at the scrub position.
  const beforePoint = pointAt(progress, before);
  const afterPoint = pointAt(progress, after);

  const beforeHalted = beforePoint?.emergency_stop === true || beforePoint?.status === "EMERGENCY_STOP";
  const afterGoal = afterPoint?.status === "GOAL_REACHED";
  const beforeStopX = before?.stop_coordinate?.x ?? beforePoint?.x ?? 0;
  const maxDistance = 24.0;

  const beforeX = Math.max(0, Math.min(maxDistance, beforePoint?.x ?? 0));
  const afterX = Math.max(0, Math.min(maxDistance, afterPoint?.x ?? 0));

  const deltaBadge = useMemo(() => {
    if (!delta) return null;
    const v = delta.reproduction_rate;
    if (v === null || v === undefined) return { label: "No delta", tone: "muted" as const };
    if (v < 0) return { label: `${Math.round(v * 100)}% failure rate`, tone: "success" as const };
    if (v > 0) return { label: `+${Math.round(v * 100)}% failure rate`, tone: "danger" as const };
    return { label: "No change in failure rate", tone: "muted" as const };
  }, [delta]);

  const afterPanelTitle = patch?.candidate_id
    ? `Post-Patch Digital Twin (${patch.candidate_id} Applied)`
    : "Post-Patch Digital Twin (Patch Applied)";

  // Export the real replay data (both twin sides + the patch)
  const handleExportReplay = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        incident_id: incidentId,
        experiment: replayData?.experiment ?? null,
        applied_configuration: replayData?.applied_configuration ?? {},
        before,
        after,
        delta,
        verdict: replayData?.verdict ?? null,
        freshness_budget_ms: budget,
        patch,
        verification: replayData?.verification ?? null,
        exported_at: new Date().toISOString(),
      };
      const replayStr = JSON.stringify(payload, null, 2);
      const blob = new Blob([replayStr], { type: "application/json" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `victory-replay-${incidentId.slice(0, 8)}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Replay dataset exported successfully!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to export replay", "error");
    } finally {
      setLoading(false);
    }
  };

  // Test rollback functionality via backend applyPatch rollback
  const handleTestRollback = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Testing reversible rollback safety mechanism...", "info");
      const result: ApplyPatchResult = await api.applyPatch(incidentId, ".", false, true);

      if (result.success) {
        setRollbackStatus("VERIFIED_REVERSIBLE");
        notify("Rollback test passed! Verified patch is cleanly and safely reversible.", "success");
      } else {
        setRollbackStatus("FAILED");
        notify("Rollback test returned unexpected status: " + (result.message || "check workspace"), "info");
      }
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Rollback execution failed", "error");
    } finally {
      setLoading(false);
    }
  };

  // Open inspector for the pre-patch side, populated from the real twin run.
  const handleOpenBeforeInspector = () => {
    if (!before) return;
    const data: InspectorData = {
      mode: "experiment",
      experimentId: "pre-patch-baseline",
      experimentData: {
        name: "Pre-Patch Baseline (Failure)",
        type: "Digital Twin Simulation",
        status: before.reproduction_count > 0 ? "FAILED" : "SUCCESS",
        reproduction_rate: before.reproduction_rate,
        trial_count: before.trial_count,
        reproduction_count: before.reproduction_count,
        intervention: "No patch applied — original fault configuration",
        confidence: Math.round((1 - before.reproduction_rate) * 100),
        failure_oracle: {
          avg_total_latency: before.avg_latency_ms,
          max_total_latency: before.max_latency_ms,
          freshness_budget_ms: budget,
        },
        limitations: [
          "Digital twin simulation only — not a physical robot",
          `${before.reproduction_count}/${before.trial_count} trials tripped the freshness interlock`,
          before.halt_reason ?? "No halt reason recorded",
        ],
        metrics: {
          batch_wait_ms: before.avg_batch_wait_ms,
          gpu_compute_ms: before.avg_gpu_compute_ms,
          network_delay_ms: before.avg_network_delay_ms,
          avg_total_latency: before.avg_latency_ms,
          p99_total_latency: before.p99_latency_ms,
          halt_coordinate: before.stop_coordinate,
        },
      },
    };
    openInspector("experiment", data);
  };

  // Open inspector for the post-patch side, populated from the real twin run.
  const handleOpenAfterInspector = () => {
    if (!after) return;
    const data: InspectorData = {
      mode: "experiment",
      experimentId: patch?.candidate_id ?? "post-patch",
      experimentData: {
        name: patch?.title ?? "Post-Patch Twin",
        type: "Digital Twin Simulation",
        status: after.reproduction_count === 0 ? "SUCCESS" : "FAILED",
        reproduction_rate: after.reproduction_rate,
        trial_count: after.trial_count,
        reproduction_count: after.reproduction_count,
        intervention:
          patch?.unified_diff ||
          replayData?.experiment?.intervention ||
          "Patch configuration applied to the twin",
        confidence: Math.round((1 - after.reproduction_rate) * 100),
        failure_oracle: {
          avg_total_latency: after.avg_latency_ms,
          max_total_latency: after.max_latency_ms,
          freshness_budget_ms: budget,
        },
        limitations: [
          "Digital twin simulation only — not a physical robot",
          `${after.goal_reached_count}/${after.trial_count} trials reached the goal`,
          `Average latency ${after.avg_latency_ms}ms against a ${budget}ms budget`,
        ],
        metrics: {
          batch_wait_ms: after.avg_batch_wait_ms,
          gpu_compute_ms: after.avg_gpu_compute_ms,
          network_delay_ms: after.avg_network_delay_ms,
          avg_total_latency: after.avg_latency_ms,
          p99_total_latency: after.p99_latency_ms,
          goal_reached: after.goal_reached_count,
        },
      },
    };
    openInspector("experiment", data);
  };

  // Open inspector for the patch, populated from the real patch candidate.
  const handleOpenPatchInspector = () => {
    if (!patch) return;
    const verification = replayData?.verification ?? null;
    const data: InspectorData = {
      mode: "patch",
      patchId: patch.candidate_id ?? patch.id,
      patchData: {
        title: patch.title,
        candidate_id: patch.candidate_id ?? patch.id,
        score: patch.score,
        verified: patch.verified,
        lines_changed: patch.lines_changed,
        affected_files: patch.affected_files,
        unified_diff: patch.unified_diff || patch.diff,
        applied_cleanly: patch.applied_cleanly,
        regression_test_passes_after: patch.regression_test_passes_after,
        original_failure_not_reproduced: patch.original_failure_not_reproduced,
        existing_tests_pass: patch.existing_tests_pass,
        safety_invariants_pass: patch.safety_invariants_pass,
        performance_within_budget: patch.performance_within_budget,
        forbidden_change_scan_passes: patch.forbidden_change_scan_passes,
        rollback_test_passes: patch.rollback_test_passes,
        rationale: patch.rationale,
        type: "Code Fix",
        confidence: Math.round(patch.score * 100),
        limitations: verification
          ? [verification.message]
          : ["No verification report recorded for this patch"],
      },
    };
    openInspector("patch", data);
  };

  // Download validated patch
  const handleDownloadPatch = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Downloading validated patch package...", "info");
      const blob = await api.downloadPatchPackage(incidentId);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-victory-patch-${incidentId.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Patch package downloaded. Ready for deployment.", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Download failed", "error");
    } finally {
      setLoading(false);
    }
  };

  /** Render one metric row, with an improvement arrow when the delta is meaningful. */
  const renderDelta = (value: number | null | undefined, lowerIsBetter = true) => {
    if (value === null || value === undefined) {
      return <span className="font-mono text-[var(--color-fg-muted)]">—</span>;
    }
    if (value === 0) {
      return <span className="font-mono text-[var(--color-fg-muted)]">No change</span>;
    }
    const improved = lowerIsBetter ? value < 0 : value > 0;
    const color = improved
      ? "text-[var(--color-success-fg)]"
      : "text-[var(--color-danger-fg)]";
    return (
      <span className={`font-mono ${color}`}>
        {value > 0 ? "+" : ""}
        {value}
        {improved ? " (improved)" : " (regressed)"}
      </span>
    );
  };

  return (
    <div className="w-full space-y-5">
      {/* Header */}
      <PageHeader
        title="Victory Replay"
        subtitle="Before vs. after digital-twin validation and reversible rollback confirmation"
        badge={
          <Badge
            tone={replayData?.verdict?.failure_eliminated ? "success" : replayData?.verdict?.regression_introduced ? "danger" : "secondary"}
            dot={true}
          >
            {replayData?.verdict?.failure_eliminated
              ? "Patch Eliminates Failure (Twin-Verified)"
              : replayData?.verdict?.regression_introduced
                ? "Regression Introduced"
                : hasComparison
                  ? "Comparison Available"
                  : "No Comparison Yet"}
          </Badge>
        }
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => incidentId && loadReplay(incidentId)}
            disabled={loading || !incidentId}
            className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            {loading ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5 mr-1.5" />}
            Re-run Twin Comparison
          </Button>
        }
      />

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-[var(--color-danger-muted)] border border-[var(--color-danger-muted)]/30 rounded-[var(--radius-md)] text-[var(--color-danger-fg)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
            Dismiss
          </button>
        </div>
      )}

      {!hasComparison ? (
        <Panel padding="none">
          <PanelSection dividerBefore={false}>
            <EmptyState
              icon={EmptyStateIcons.network}
              title={replayLoaded ? "No twin comparison available" : "Running the before/after twin comparison..."}
              description={
                replayLoaded
                  ? replayData?.reason ??
                    "This incident has no simulated experiment branch yet. Run the Ghost Lab twin simulations to generate one, then the before/after comparison will appear here."
                  : "The backend is running both sides of the digital twin over identical seeds."
              }
              action={
                replayLoaded ? (
                  <span className="inline-flex items-center gap-2">
                    Re-run Twin Comparison
                  </span>
                ) : undefined
              }
            />
          </PanelSection>
        </Panel>
      ) : (
        <>
          {/* Headline stats — every value measured by the twin */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Failure Rate (Before)"
              value={`${Math.round((before?.reproduction_rate ?? 0) * 100)}%`}
              sub={`${before?.reproduction_count ?? 0}/${before?.trial_count ?? 0} emergency stops`}
              trend={(before?.reproduction_count ?? 0) > 0 ? "danger" : "success"}
            />
            <Stat
              label="Failure Rate (After)"
              value={`${Math.round((after?.reproduction_rate ?? 0) * 100)}%`}
              sub={`${after?.reproduction_count ?? 0}/${after?.trial_count ?? 0} emergency stops`}
              trend={(after?.reproduction_count ?? 0) > 0 ? "danger" : "success"}
            />
            <Stat
              label="Goal Reached (After)"
              value={`${after?.goal_reached_count ?? 0}/${after?.trial_count ?? 0}`}
              sub={
                after?.is_confirmed_safe
                  ? "All trials completed the route"
                  : "Not every trial completed"
              }
              trend={after?.is_confirmed_safe ? "success" : "warning"}
            />
            <Stat
              label="P99 Latency Delta"
              value={
                delta?.p99_latency_ms !== null && delta?.p99_latency_ms !== undefined
                  ? `${delta.p99_latency_ms > 0 ? "+" : ""}${delta.p99_latency_ms}ms`
                  : "—"
              }
              sub={
                before && after
                  ? `${before.p99_latency_ms}ms → ${after.p99_latency_ms}ms (budget ${budget}ms)`
                  : "No latency data"
              }
              trend={
                delta?.p99_latency_ms !== null && delta?.p99_latency_ms !== undefined
                  ? delta.p99_latency_ms < 0
                    ? "success"
                    : delta.p99_latency_ms > 0
                      ? "danger"
                      : "muted"
                  : "muted"
              }
            />
          </div>

          {/* Main Content - Using PanelStack */}
          <PanelStack space="lg">
            {/* Panel 1: Synchronized Twin Comparison - Before/After */}
            <Panel title="Digital Twin Comparison" subtitle="Baseline failure vs. patched success replay with synchronized playback">
              {/* Synchronized Playback Scrubbing Toolbar */}
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 text-xs bg-[var(--color-canvas-subtle)] p-2.5 rounded-[var(--radius-md)] border border-[var(--color-border-default)]">
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsPlaying(!isPlaying)}
                    className="h-8 px-2.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    {isPlaying ? <PauseIcon className="h-4 w-4 mr-1 text-[var(--color-attention-fg)]" /> : <Play className="h-4 w-4 mr-1 text-[var(--color-success-fg)]" />}
                    {isPlaying ? "Pause Both" : "Play Replay"}
                  </Button>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => { setProgress(0.0); setIsPlaying(true); }}
                    className="h-8 px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    <RotateCcw className="h-3.5 w-3.5 mr-1" />
                    Reset
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

                {/* Scrubber */}
                <div className="flex-1 max-w-sm flex items-center gap-2">
                  <span className="font-mono text-[10px] text-[var(--color-fg-muted)]">
                    {(progress * 100).toFixed(0)}%
                  </span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.01"
                    value={progress}
                    aria-label="Replay timeline progress"
                    onChange={(e) => {
                      setProgress(parseFloat(e.target.value));
                      setIsPlaying(false);
                    }}
                    className="w-full accent-[var(--color-accent-fg)] h-1.5 bg-[var(--color-border-default)] rounded cursor-pointer"
                  />
                </div>

                {deltaBadge && (
                  <Badge tone={deltaBadge.tone}>{deltaBadge.label}</Badge>
                )}
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                {/* Before Patch (Failure) */}
                <PanelSection title="Pre-Patch Digital Twin (Baseline Failure)">
                  <button
                    onClick={handleOpenBeforeInspector}
                    className="w-full aspect-video bg-[var(--color-canvas-subtle)] rounded-[var(--radius-md)] overflow-hidden relative border border-[var(--color-danger-muted)]/30 p-4 flex flex-col justify-between hover:ring-1 hover:ring-[var(--color-danger-muted)]/50 transition-shadow cursor-pointer text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[var(--color-danger-fg)] font-bold flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-[var(--color-danger-fg)]" />
                        INCIDENT {incidentId || "CAU-0001"} — UNPATCHED
                      </span>
                      <Badge tone="danger">
                        {before?.reproduction_count ?? 0}/{before?.trial_count ?? 0} Emergency Stops
                      </Badge>
                    </div>

                    {/* Animated Simulation Viewport */}
                    <div className="relative my-2 w-full h-24 bg-[var(--color-canvas)] rounded-[var(--radius-sm)] border border-[var(--color-danger-muted)]/30 flex items-center px-4 overflow-hidden">
                      <span className="absolute left-2 top-1 text-[9px] font-mono text-[var(--color-fg-muted)]">Start (0m)</span>
                      <span className="absolute right-2 top-1 text-[9px] font-mono text-[var(--color-fg-muted)]">Goal (24m)</span>

                      {/* Track line */}
                      <div className="w-full h-1 bg-[var(--color-border-default)] relative">
                        {/* Halting line */}
                        <div
                          className="h-full bg-[var(--color-danger-fg)] relative"
                          style={{ width: `${(beforeX / maxDistance) * 100}%` }}
                        >
                          <div className="absolute right-0 -top-3 w-6 h-6 rounded-full bg-[var(--color-danger-fg)] text-[var(--color-fg-on-emphasis)] flex items-center justify-center text-xs font-bold shadow-md">
                            {beforeHalted ? "!" : "AMR"}
                          </div>
                        </div>
                      </div>

                      {beforeHalted && beforePoint && (
                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[var(--color-danger-muted)]/90 border border-[var(--color-danger-fg)] text-[var(--color-danger-fg)] text-[11px] font-bold px-2.5 py-1 rounded shadow">
                          HALTED: Stale Detection ({beforePoint.latency_ms}ms {">"} {budget}ms)
                        </div>
                      )}
                    </div>

                    <div className="space-y-1">
                      <p className="text-sm font-bold text-[var(--color-fg-default)] flex items-center gap-1.5">
                        <AlertTriangle className="h-4 w-4 text-[var(--color-danger-fg)]" />
                        {before?.emergency_stop_count ? "Emergency Stop Tripped" : "No emergency stop recorded"}
                      </p>
                      <p className="text-xs text-[var(--color-fg-muted)]">
                        {before?.halt_reason
                          ? `${before.halt_reason} (halted at x=${beforeStopX.toFixed(1)}m).`
                          : `Robot travelled ${before?.stop_coordinate?.x?.toFixed(1) ?? "0.0"}m before the interlock.`}
                      </p>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Batch Window</span>
                        <div className="font-mono text-[var(--color-danger-fg)] font-bold">
                          {before?.parameters?.batching_window_ms ?? "—"}ms
                        </div>
                      </div>
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">P99 Latency</span>
                        <div className="font-mono text-[var(--color-danger-fg)] font-bold">{before?.p99_latency_ms ?? "—"}ms</div>
                      </div>
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Safety Interlock</span>
                        <div className="font-mono text-[var(--color-danger-fg)] font-bold">
                          {beforeHalted ? "HALTED" : before?.emergency_stop_count ? "TRIPPED" : "NOMINAL"}
                        </div>
                      </div>
                    </div>
                  </button>
                </PanelSection>

                {/* After Patch (Success) */}
                <PanelSection title={afterPanelTitle}>
                  <button
                    onClick={handleOpenAfterInspector}
                    className="w-full aspect-video bg-[var(--color-canvas-subtle)] rounded-[var(--radius-md)] overflow-hidden relative border border-[var(--color-success-muted)]/30 p-4 flex flex-col justify-between hover:ring-1 hover:ring-[var(--color-success-muted)]/50 transition-shadow cursor-pointer text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono text-[var(--color-success-fg)] font-bold flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-[var(--color-success-fg)]" />
                        PATCHED — {patch?.candidate_id ?? "intervention applied"}
                      </span>
                      <Badge tone="success">
                        {after?.goal_reached_count ?? 0}/{after?.trial_count ?? 0} Runs Nominal
                      </Badge>
                    </div>

                    {/* Animated Simulation Viewport */}
                    <div className="relative my-2 w-full h-24 bg-[var(--color-canvas)] rounded-[var(--radius-sm)] border border-[var(--color-success-muted)]/30 flex items-center px-4 overflow-hidden">
                      <span className="absolute left-2 top-1 text-[9px] font-mono text-[var(--color-fg-muted)]">Start (0m)</span>
                      <span className="absolute right-2 top-1 text-[9px] font-mono text-[var(--color-fg-muted)]">Goal (24m)</span>

                      {/* Track line */}
                      <div className="w-full h-1 bg-[var(--color-border-default)] relative">
                        <div
                          className="h-full bg-[var(--color-success-fg)] relative"
                          style={{ width: `${(afterX / maxDistance) * 100}%` }}
                        >
                          <div className="absolute right-0 -top-3 w-6 h-6 rounded-full bg-[var(--color-success-fg)] text-[var(--color-fg-on-emphasis)] flex items-center justify-center text-xs font-bold shadow-md">
                            {afterGoal ? <Check className="h-3.5 w-3.5" /> : "AMR"}
                          </div>
                        </div>
                      </div>

                      {afterGoal && (
                        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-[var(--color-success-muted)]/90 border border-[var(--color-success-fg)] text-[var(--color-success-fg)] text-[11px] font-bold px-2.5 py-1 rounded shadow">
                          ✓ ROUTE COMPLETED
                        </div>
                      )}
                    </div>

                    <div className="space-y-1">
                      <p className="text-sm font-bold text-[var(--color-fg-default)] flex items-center gap-1.5">
                        <ShieldCheck className="h-4 w-4 text-[var(--color-success-fg)]" />
                        {after?.is_confirmed_safe ? "Route Completed Successfully" : "Route Incomplete"}
                      </p>
                      <p className="text-xs text-[var(--color-fg-muted)]">
                        {afterPoint
                          ? `Robot at x=${afterPoint.x.toFixed(1)}m. Perception age: ${afterPoint.latency_ms}ms ${afterPoint.latency_ms <= budget ? "<=" : ">"} ${budget}ms freshness budget.`
                          : "No trajectory recorded for the patched configuration."}
                      </p>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Batch Window</span>
                        <div className="font-mono text-[var(--color-success-fg)] font-bold">
                          {after?.parameters?.batching_window_ms ?? "—"}ms
                        </div>
                      </div>
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">P99 Latency</span>
                        <div className="font-mono text-[var(--color-success-fg)] font-bold">{after?.p99_latency_ms ?? "—"}ms</div>
                      </div>
                      <div className="p-1.5 rounded bg-[var(--color-canvas)]/40 border border-[var(--color-border-muted)]">
                        <span className="text-[var(--color-fg-muted)] text-[10px] uppercase block">Safety Interlock</span>
                        <div className="font-mono text-[var(--color-success-fg)] font-bold">
                          {after?.emergency_stop_count ? "TRIPPED" : "NOMINAL"}
                        </div>
                      </div>
                    </div>
                  </button>
                </PanelSection>
              </div>

              {/* Configuration actually compared */}
              <PanelDivider label="Configurations Compared (twin fault profile)" />
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] mb-2">
                    Before (unpatched)
                  </p>
                  <KV label="Batching Window" value={`${before?.parameters?.batching_window_ms ?? "—"} ms`} />
                  <KV label="QoS Queue Depth" value={before?.parameters?.qos_queue_depth ?? "—"} />
                  <KV label="Clock Skew" value={`${before?.parameters?.clock_skew_ms ?? "—"} ms`} />
                  <KV label="Freshness Budget" value={`${budget} ms`} />
                </div>
                <div className="rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] p-3">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-muted)] mb-2">
                    After (patched)
                  </p>
                  <KV label="Batching Window" value={`${after?.parameters?.batching_window_ms ?? "—"} ms`} />
                  <KV label="QoS Queue Depth" value={after?.parameters?.qos_queue_depth ?? "—"} />
                  <KV label="Clock Skew" value={`${after?.parameters?.clock_skew_ms ?? "—"} ms`} />
                  <KV label="Freshness Budget" value={`${budget} ms`} />
                </div>
              </div>
            </Panel>

            {/* Panel 2: Metrics Delta Table */}
            <Panel title="Key Performance & Safety Metrics Comparison" subtitle="Quantitative delta analysis across critical safety and performance indicators">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-[var(--color-border-default)] text-xs">
                  <thead>
                    <tr className="bg-[var(--color-canvas-inset)]">
                      <th className="px-4 py-3 text-left font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider text-[11px]">Metric</th>
                      <th className="px-4 py-3 text-left font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider text-[11px]">Before Patch</th>
                      <th className="px-4 py-3 text-left font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider text-[11px]">After Patch</th>
                      <th className="px-4 py-3 text-left font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider text-[11px]">Improvement</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border-default)]">
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Emergency Stop Failure Count</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">
                        {before?.reproduction_count ?? "—"} / {before?.trial_count ?? "—"}
                      </td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">
                        {after?.reproduction_count ?? "—"} / {after?.trial_count ?? "—"}
                      </td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.reproduction_rate ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Perception Detection Age (P99)</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">{before?.p99_latency_ms ?? "—"}ms</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">{after?.p99_latency_ms ?? "—"}ms</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.p99_latency_ms ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Average Perception Latency</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">{before?.avg_latency_ms ?? "—"}ms</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">{after?.avg_latency_ms ?? "—"}ms</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.avg_latency_ms ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Dynamic Batching Wait (avg)</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">{before?.avg_batch_wait_ms ?? "—"}ms</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">{after?.avg_batch_wait_ms ?? "—"}ms</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.avg_batch_wait_ms ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">GPU Inference Compute (avg)</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-muted)]">{before?.avg_gpu_compute_ms ?? "—"}ms</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-fg-muted)]">{after?.avg_gpu_compute_ms ?? "—"}ms</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.avg_gpu_compute_ms ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Network Delivery Delay (avg)</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-muted)]">{before?.avg_network_delay_ms ?? "—"}ms</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-fg-muted)]">{after?.avg_network_delay_ms ?? "—"}ms</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.avg_network_delay_ms ?? null, true)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Route Completion Count</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">{before?.goal_reached_count ?? "—"}</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">{after?.goal_reached_count ?? "—"}</td>
                      <td className="px-4 py-3">
                        {renderDelta(delta?.goal_reached_count ?? null, false)}
                      </td>
                    </tr>
                    <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-canvas-subtle)]/50 transition-colors">
                      <td className="px-4 py-3 font-medium text-[var(--color-fg-default)]">Safety Watchdog Invariant State</td>
                      <td className="px-4 py-3 font-mono text-[var(--color-danger-fg)] font-bold">
                        {before?.emergency_stop_count ? "VIOLATED" : "NOMINAL"}
                      </td>
                      <td className="px-4 py-3 font-mono text-[var(--color-success-fg)] font-bold">
                        {after?.emergency_stop_count ? "VIOLATED" : "NOMINAL"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`font-mono ${
                            replayData?.verdict?.failure_eliminated
                              ? "text-[var(--color-success-fg)]"
                              : replayData?.verdict?.regression_introduced
                                ? "text-[var(--color-danger-fg)]"
                                : "text-[var(--color-fg-muted)]"
                          }`}
                        >
                          {replayData?.verdict?.failure_eliminated
                            ? "RESTORED"
                            : replayData?.verdict?.regression_introduced
                              ? "BROKEN"
                              : "UNCHANGED"}
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Verification report — real booleans from the backend verifier */}
              {replayData?.verification && (
                <>
                  <PanelDivider label="Verification Report (backend verifier)" />
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] p-3 space-y-2">
                      <KV label="Overall Passed" value={replayData.verification.passed ? "YES" : "NO"} />
                      <KV label="Applied Cleanly" value={replayData.verification.applies_cleanly ? "YES" : "NO"} />
                      <KV label="Regression Test Fails Before" value={replayData.verification.regression_test_fails_before ? "YES" : "NO"} />
                      <KV label="Regression Test Passes After" value={replayData.verification.regression_test_passes_after ? "YES" : "NO"} />
                    </div>
                    <div className="rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] p-3 space-y-2">
                      <KV label="Original Failure Not Reproduced" value={replayData.verification.original_failure_not_reproduced ? "YES" : "NO"} />
                      <KV label="Existing Tests Pass" value={replayData.verification.existing_tests_pass ? "YES" : "NO"} />
                      <KV label="Safety Invariants Pass" value={replayData.verification.safety_invariants_pass ? "YES" : "NO"} />
                      <KV label="Performance Within Budget" value={replayData.verification.performance_within_budget ? "YES" : "NO"} />
                    </div>
                  </div>
                  {replayData.verification.message && (
                    <p className="mt-3 text-xs text-[var(--color-fg-muted)] leading-relaxed">
                      {replayData.verification.message}
                    </p>
                  )}
                </>
              )}
            </Panel>

            {/* Panel 3: Rollback Verification & Patch Download */}
            <Panel title="Verification & Deployment" subtitle="Reversible rollback safety check and production patch package">
              <div className="grid gap-5 lg:grid-cols-2">
                <PanelSection title="Rollback Safety Verification">
                  <div className="w-full p-4 rounded-[var(--radius-md)] border bg-[var(--color-canvas-subtle)] border-[var(--color-border-default)] transition-all text-left space-y-4">
                    <p className="text-xs text-[var(--color-fg-muted)] leading-relaxed">
                      Before applying in production, Cauveris tests automated rollback to ensure that reverting the patch immediately restores baseline system behavior without leftover state or side effects. This executes the real installer script against the target workspace.
                    </p>
                    {rollbackStatus && (
                      <div className={`p-3 rounded-[var(--radius-md)] border text-xs flex items-center gap-2 ${
                        rollbackStatus === "VERIFIED_REVERSIBLE"
                          ? "bg-[var(--color-success-muted)] border-[var(--color-success-muted)]/30 text-[var(--color-success-fg)]"
                          : "bg-[var(--color-danger-muted)] border-[var(--color-danger-muted)]/30 text-[var(--color-danger-fg)]"
                      }`}>
                        <Check className="h-3.5 w-3.5 flex-shrink-0" />
                        <span>
                          {rollbackStatus === "VERIFIED_REVERSIBLE"
                            ? "Safety invariant verified: Rollback cleanly restores baseline without file corruption."
                            : "Rollback did not report success. Check the target workspace."}
                        </span>
                      </div>
                    )}
                    <div className="flex flex-wrap items-center gap-2 pt-2">
                      <Button variant="danger" size="sm" onClick={() => handleTestRollback()} disabled={loading}>
                        <RotateCcw className="h-3.5 w-3.5" />
                        <span>{loading ? "Testing..." : "Test Reversible Rollback"}</span>
                      </Button>
                      <Button variant="outline" size="sm" onClick={() => handleExportReplay()} disabled={loading}>
                        <Download className="h-3.5 w-3.5" />
                        <span>{loading ? "Exporting..." : "Export Replay JSON"}</span>
                      </Button>
                    </div>
                  </div>
                </PanelSection>

                <PanelSection title="Download Production Patch">
                  <div className="w-full p-4 rounded-[var(--radius-md)] border bg-[var(--color-canvas-subtle)] border-[var(--color-border-default)] transition-all text-left space-y-4">
                    <p className="text-xs text-[var(--color-fg-muted)] leading-relaxed">
                      Download the complete verified patch package including universal unified diff, self-contained executable Python installer, and reviewer checklist.
                    </p>
                    {patch && (
                      <div className="space-y-2">
                        <KV label="Candidate" value={patch.candidate_id ?? patch.id ?? "—"} />
                        <KV label="Verified" value={patch.verified ? "YES" : "NO"} />
                        <KV label="Score" value={patch.score?.toFixed(2) ?? "—"} />
                        <KV label="Files Affected" value={patch.affected_files?.length ?? 0} />
                      </div>
                    )}
                    <div className="pt-2">
                      <Button variant="primary" size="md" onClick={() => handleDownloadPatch()} disabled={loading} className="w-auto min-w-[220px]">
                        {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4" />}
                        <span>{loading ? "Downloading..." : "Download Patch Package"}</span>
                      </Button>
                    </div>
                  </div>
                </PanelSection>
              </div>
            </Panel>
          </PanelStack>
        </>
      )}
    </div>
  );
}
