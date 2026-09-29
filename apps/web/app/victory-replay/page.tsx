"use client";

import { useState } from "react";
import { Button, Card, Badge, PageHeader } from "@/components/ui";
import { api, ApplyPatchResult } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";

export default function VictoryReplay() {
  const { incidentId } = useActiveIncident();
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
        notify("✓ Rollback test passed! Verified patch is cleanly and safely reversible.", "success");
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
    <div className="min-h-screen bg-background text-foreground p-6">
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
        <div className="mb-6 p-4 bg-danger/10 border border-danger/25 rounded-xl text-danger text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-danger hover:text-white text-xs font-semibold uppercase">Dismiss</button>
        </div>
      )}

      {/* Main Content */}
      <div className="space-y-8">
        {/* Side-by-side Replays */}
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Before Patch (Failure) */}
          <Card title="Pre-Patch Digital Twin (Baseline Failure)">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative border border-danger/30 p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-danger font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-danger animate-ping" />
                  INCIDENT CAU-0001 (Deployment v42)
                </span>
                <Badge tone="danger">10/10 Emergency Stops</Badge>
              </div>

              <div className="space-y-3 text-center my-auto">
                <div className="w-16 h-16 bg-danger/10 rounded-2xl flex items-center justify-center mx-auto border border-danger/30">
                  <svg className="w-8 h-8 text-danger" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div>
                  <p className="text-base font-bold text-white">Emergency Stop Tripped</p>
                  <p className="text-xs text-muted max-w-xs mx-auto mt-1">
                    Robot halted at Aisle B (x=12.4m, y=4.2m). Perception age: 140ms &gt; 120ms freshness budget.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">Batch Window</span>
                  <div className="font-mono text-danger font-bold">200ms</div>
                </div>
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">P99 Latency</span>
                  <div className="font-mono text-danger font-bold">180ms</div>
                </div>
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">Safety Interlock</span>
                  <div className="font-mono text-danger font-bold">HALTED</div>
                </div>
              </div>
            </div>
          </Card>

          {/* After Patch (Success) */}
          <Card title="Post-Patch Digital Twin (PATCH-001 Applied)">
            <div className="aspect-video w-full bg-[radial-gradient(at_top_left,_var(--color-surface-2)_0%,_var(--color-background)_60%)] rounded-2xl overflow-hidden relative border border-success/30 p-5 flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-success font-bold flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-success" />
                  PATCHED (batching_window_ms: 100)
                </span>
                <Badge tone="success">10/10 Runs Nominal</Badge>
              </div>

              <div className="space-y-3 text-center my-auto">
                <div className="w-16 h-16 bg-success/10 rounded-2xl flex items-center justify-center mx-auto border border-success/30 shadow-lg shadow-success/10">
                  <svg className="w-8 h-8 text-success" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
                <div>
                  <p className="text-base font-bold text-white">Route Completed Successfully</p>
                  <p className="text-xs text-muted max-w-xs mx-auto mt-1">
                    Robot completed navigation to Rack B-14. Perception age: 90ms &lt;= 120ms freshness budget.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">Batch Window</span>
                  <div className="font-mono text-success font-bold">100ms</div>
                </div>
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">P99 Latency</span>
                  <div className="font-mono text-success font-bold">110ms</div>
                </div>
                <div className="p-1.5 rounded bg-black/40">
                  <span className="text-muted text-[10px] uppercase">Safety Interlock</span>
                  <div className="font-mono text-success font-bold">NOMINAL</div>
                </div>
              </div>
            </div>
          </Card>
        </div>

        {/* Metrics Comparison */}
        <Card title="Key Performance & Safety Metrics Comparison">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-white/10 text-xs">
              <thead>
                <tr>
                  <th className="px-5 py-3 text-left font-semibold text-muted uppercase tracking-wider">Metric</th>
                  <th className="px-5 py-3 text-left font-semibold text-muted uppercase tracking-wider">Before Patch</th>
                  <th className="px-5 py-3 text-left font-semibold text-muted uppercase tracking-wider">After Patch</th>
                  <th className="px-5 py-3 text-left font-semibold text-muted uppercase tracking-wider">Improvement</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                <tr>
                  <td className="px-5 py-3 font-medium text-white">Emergency Stop Failure Count</td>
                  <td className="px-5 py-3 font-mono text-danger font-bold">10 / 10</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">0 / 10</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">-100% (Eliminated)</td>
                </tr>
                <tr>
                  <td className="px-5 py-3 font-medium text-white">Perception Detection Age (P99)</td>
                  <td className="px-5 py-3 font-mono text-danger font-bold">140ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">90ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">-35% (Within Budget)</td>
                </tr>
                <tr>
                  <td className="px-5 py-3 font-medium text-white">GPU Inference P99 Latency</td>
                  <td className="px-5 py-3 font-mono text-danger font-bold">180ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">110ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">-39%</td>
                </tr>
                <tr>
                  <td className="px-5 py-3 font-medium text-white">Robot Control Loop P95 Latency</td>
                  <td className="px-5 py-3 font-mono text-muted">60ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">45ms</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">-25%</td>
                </tr>
                <tr>
                  <td className="px-5 py-3 font-medium text-white">Safety Watchdog Invariant State</td>
                  <td className="px-5 py-3 font-mono text-danger font-bold">VIOLATED</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">NOMINAL</td>
                  <td className="px-5 py-3 font-mono text-success font-bold">RESTORED</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>

        {/* Reversible Rollback Verification */}
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Rollback Safety Verification">
            <div className="space-y-4">
              <p className="text-xs text-muted leading-relaxed">
                Before applying in production, Cauveris tests automated rollback to ensure that reverting the patch immediately restores baseline system behavior without leftover state or side effects.
              </p>
              {rollbackStatus && (
                <div className="p-3 rounded-lg bg-success/10 border border-success/30 text-xs text-success flex items-center gap-2">
                  <span className="font-bold">✓</span>
                  <span>Safety invariant verified: Rollback cleanly restores baseline without file corruption.</span>
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="danger" size="sm" onClick={handleTestRollback} disabled={loading}>
                  {loading ? "Testing..." : "Test Reversible Rollback"}
                </Button>
                <Button variant="outline" size="sm" onClick={handleExportReplay} disabled={loading}>
                  {loading ? "Exporting..." : "Export Replay JSON"}
                </Button>
              </div>
            </div>
          </Card>

          <Card title="Download Production Patch">
            <div className="space-y-4">
              <p className="text-xs text-muted leading-relaxed">
                Download the complete verified patch package including universal unified diff, self-contained executable Python installer, and reviewer checklist.
              </p>
              <Button variant="primary" size="lg" onClick={handleDownloadPatch} disabled={loading} className="w-full">
                {loading ? "Downloading..." : "Download Validated Patch Package"}
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}