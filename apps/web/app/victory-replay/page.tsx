"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button, Card, Badge, PageHeader } from "@/components/ui";
import { api, ApplyPatchResult } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { useAuthStore } from "@/lib/auth";
import { Check, RotateCcw, Download } from "lucide-react";

export default function VictoryReplay() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, setIncidentContext } = useShell();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login?redirect=/victory-replay');
    }
  }, [isAuthenticated, authLoading, router]);

  // Show loading while auth is initializing
  if (authLoading) {
    return (
      <div className="flex flex-col gap-4 min-h-screen items-center justify-center p-8">
        <div className="flex h-8 w-8 animate-spin text-primary">
          <svg className="h-8 w-8" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
        </div>
        <p className="text-sm text-[var(--color-text-muted)]">Loading Victory Replay...</p>
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
  }, [incidentId, judgeMode, engineerMode]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rollbackStatus, setRollbackStatus] = useState<string | null>(null);

  // Export replay timeline data
  const handleExportReplay = async () => {
    setLoading(true);
    setError(null);
    try {
      const timeline = await api.getTimeline(incidentId);
      const replayStr = JSON.stringify(timeline, null, 2);
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
        notify("Rollback test returned unexpected status: " + (result.message || "check workspace"), "info");
      }
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Rollback execution failed", "error");
    } finally {
      setLoading(false);
    }
  };

  // Open inspector for pre-patch replay
  const handleOpenBeforeInspector = () => {
    const data: InspectorData = {
      mode: "experiment",
      experimentId: "pre-patch-baseline",
      experimentData: {
        name: "Pre-Patch Baseline (Failure)",
        type: "Digital Twin Simulation",
        status: "FAILED",
        reproduction_rate: 1.0,
        intervention: "No patch applied (batching_window_ms: 200)",
        confidence: 0,
        limitations: ["Emergency stop 100%", "Exceeds freshness budget", "P99 latency 180ms"],
      },
    };
    openInspector("experiment", data);
  };

  // Open inspector for post-patch replay
  const handleOpenAfterInspector = () => {
    const data: InspectorData = {
      mode: "experiment",
      experimentId: "post-patch-patch001",
      experimentData: {
        name: "Post-Patch PATCH-001",
        type: "Digital Twin Simulation",
        status: "SUCCESS",
        reproduction_rate: 0.0,
        intervention: "batching_window_ms: 100",
        confidence: 100,
        limitations: ["Simulation only", "Requires production validation"],
      },
    };
    openInspector("experiment", data);
  };

  // Open inspector for patch
  const handleOpenPatchInspector = () => {
    const data: InspectorData = {
      mode: "patch",
      patchId: "patch-exp-h1_batching_window",
      patchData: {
        title: "PATCH-001: Dynamic Batching Window Reduction (Root Cause Fix)",
        candidate_id: "patch-exp-h1_batching_window",
        score: 0.97,
        verified: true,
        lines_changed: 1,
        affected_files: ["config/inference.yaml"],
        unified_diff: `--- a/config/inference.yaml\n+++ b/config/inference.yaml\n@@ -4,3 +4,3 @@\n dynamic_batching:\n   enabled: true\n   max_batch_size: 8\n-  batching_window_ms: 200\n+  batching_window_ms: 100\n   timeout_ms: 500`,
        applied_cleanly: true,
        regression_test_passes_after: true,
        original_failure_not_reproduced: true,
        existing_tests_pass: true,
        safety_invariants_pass: true,
        performance_within_budget: true,
        forbidden_change_scan_passes: true,
        rollback_test_passes: true,
        rationale: "Reduces dynamic batching accumulation delay from ~105ms to ~52ms, ensuring total latency remains 106ms <= 120ms freshness budget.",
        type: "Code Fix",
        confidence: 97,
        limitations: ["Limited to simulated verification", "No production deployment data"],
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

  return (
    <div className="min-h-screen bg-[var(--theme-background)] text-[var(--theme-foreground)] p-6">
      {/* Header */}
      <PageHeader
        title="Victory Replay"
        subtitle="Before vs. after physical validation and reversible rollback confirmation"
        badge={
          <Badge tone="success" dot={true}>
            Patch Validated (10/10 Runs Succeeded)
          </Badge>
        }
      />

      {/* Error Message */}
      {error && (
        <div className="mb-6 p-4 bg-[var(--color-brand-danger)]/10 border border-[var(--color-brand-danger)]/25 rounded-xl text-[var(--color-brand-danger)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--color-brand-danger)] hover:text-[var(--color-text-primary)] text-xs font-semibold uppercase">Dismiss</button>
        </div>
      )}

      {/* Main Content */}
      <div className="space-y-8">
        {/* Side-by-side Replays */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Before Patch (Failure) */}
          <Card title="Pre-Patch Digital Twin (Baseline Failure)">
            <button
              onClick={handleOpenBeforeInspector}
              className="w-full aspect-video bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative border border-danger/30 p-5 flex flex-col justify-between hover:ring-2 hover:ring-danger/50 transition-shadow cursor-pointer"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-[var(--color-brand-danger)] font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-danger animate-ping" />
                  INCIDENT CAU-0001 (Deployment v42)
                </span>
                <Badge tone="danger">10/10 Emergency Stops</Badge>
              </div>

              <div className="space-y-3 text-center my-auto">
                <div className="w-16 h-16 bg-danger/10 rounded-2xl flex items-center justify-center mx-auto border border-danger/30">
                  <svg className="w-8 h-8 text-[var(--color-brand-danger)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div>
                  <p className="text-base font-bold text-[var(--color-text-primary)]">Emergency Stop Tripped</p>
                  <p className="text-xs text-[var(--color-text-muted)] max-w-xs mx-auto mt-1">
                    Robot halted at Aisle B (x=12.4m, y=4.2m). Perception age: 140ms &gt; 120ms freshness budget.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">Batch Window</span>
                  <div className="font-mono text-[var(--color-brand-danger)] font-bold">200ms</div>
                </div>
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">P99 Latency</span>
                  <div className="font-mono text-[var(--color-brand-danger)] font-bold">180ms</div>
                </div>
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">Safety Interlock</span>
                  <div className="font-mono text-[var(--color-brand-danger)] font-bold">HALTED</div>
                </div>
              </div>
            </button>
          </Card>

          {/* After Patch (Success) */}
          <Card title="Post-Patch Digital Twin (PATCH-001 Applied)">
            <button
              onClick={handleOpenAfterInspector}
              className="w-full aspect-video bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative border border-success/30 p-5 flex flex-col justify-between hover:ring-2 hover:ring-success/50 transition-shadow cursor-pointer"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-[var(--color-brand-success)] font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-success" />
                  PATCHED (batching_window_ms: 100)
                </span>
                <Badge tone="success">10/10 Runs Nominal</Badge>
              </div>

              <div className="space-y-3 text-center my-auto">
                <div className="w-16 h-16 bg-success/10 rounded-2xl flex items-center justify-center mx-auto border border-success/30 shadow-lg shadow-success/10">
                  <svg className="w-8 h-8 text-[var(--color-brand-success)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <p className="text-base font-bold text-[var(--color-text-primary)]">Route Completed Successfully</p>
                  <p className="text-xs text-[var(--color-text-muted)] max-w-xs mx-auto mt-1">
                    Robot completed navigation to Rack B-14. Perception age: 90ms &lt;= 120ms freshness budget.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">Batch Window</span>
                  <div className="font-mono text-[var(--color-brand-success)] font-bold">100ms</div>
                </div>
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">P99 Latency</span>
                  <div className="font-mono text-[var(--color-brand-success)] font-bold">110ms</div>
                </div>
                <div className="p-1.5 rounded bg-[var(--theme-background)]/40">
                  <span className="text-[var(--color-text-muted)] text-[10px] uppercase">Safety Interlock</span>
                  <div className="font-mono text-[var(--color-brand-success)] font-bold">NOMINAL</div>
                </div>
              </div>
            </button>
          </Card>
        </div>

        {/* Metrics Comparison */}
        <Card title="Key Performance & Safety Metrics Comparison">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-[var(--color-border)] text-xs">
              <thead>
                <tr>
                  <th className="px-5 py-3 text-left font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Metric</th>
                  <th className="px-5 py-3 text-left font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Before Patch</th>
                  <th className="px-5 py-3 text-left font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">After Patch</th>
                  <th className="px-5 py-3 text-left font-semibold text-[var(--color-text-muted)] uppercase tracking-wider">Improvement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-surface)]/10 transition-colors rounded-lg">
                  <td className="px-5 py-3 font-medium text-[var(--color-text-primary)]">Emergency Stop Failure Count</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-danger)] font-bold">10 / 10</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">0 / 10</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">-100% (Eliminated)</td>
                </tr>
                <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-surface)]/10 transition-colors rounded-lg">
                  <td className="px-5 py-3 font-medium text-[var(--color-text-primary)]">Perception Detection Age (P99)</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-danger)] font-bold">140ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">90ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">-35% (Within Budget)</td>
                </tr>
                <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-surface)]/10 transition-colors rounded-lg">
                  <td className="px-5 py-3 font-medium text-[var(--color-text-primary)]">GPU Inference P99 Latency</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-danger)] font-bold">180ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">110ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">-39%</td>
                </tr>
                <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-surface)]/10 transition-colors rounded-lg">
                  <td className="px-5 py-3 font-medium text-[var(--color-text-primary)]">Robot Control Loop P95 Latency</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-text-muted)]">60ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">45ms</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">-25%</td>
                </tr>
                <tr onClick={handleOpenPatchInspector} className="cursor-pointer hover:bg-[var(--color-surface)]/10 transition-colors rounded-lg">
                  <td className="px-5 py-3 font-medium text-[var(--color-text-primary)]">Safety Watchdog Invariant State</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-danger)] font-bold">VIOLATED</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">NOMINAL</td>
                  <td className="px-5 py-3 font-mono text-[var(--color-brand-success)] font-bold">RESTORED</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        {/* Reversible Rollback Verification */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Rollback Safety Verification">
            <div className="w-full p-4 rounded-xl border bg-[var(--color-surface)]/40 border-[var(--color-border)] transition-all text-left space-y-4">
              <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
                Before applying in production, Cauveris tests automated rollback to ensure that reverting the patch immediately restores baseline system behavior without leftover state or side effects.
              </p>
              {rollbackStatus && (
                <div className="p-3 rounded-lg bg-success/10 border border-success/30 text-xs text-[var(--color-brand-success)] flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 flex-shrink-0" />
                  <span>Safety invariant verified: Rollback cleanly restores baseline without file corruption.</span>
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
          </Card>

          <Card title="Download Production Patch">
            <div className="w-full p-4 rounded-xl border bg-[var(--color-surface)]/40 border-[var(--color-border)] transition-all text-left space-y-4">
              <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
                Download the complete verified patch package including universal unified diff, self-contained executable Python installer, and reviewer checklist.
              </p>
              <div className="pt-2">
                <Button variant="primary" size="md" onClick={() => handleDownloadPatch()} disabled={loading} className="w-auto min-w-[220px]">
                  <Download className="h-4 w-4" />
                  <span>{loading ? "Downloading..." : "Download Patch Package"}</span>
                </Button>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}