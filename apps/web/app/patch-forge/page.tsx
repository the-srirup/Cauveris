"use client";

import { useState, useEffect, useMemo, Suspense, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { Button, Badge, PageHeader, Stat, Panel, PanelSection, PanelStack, PanelDivider, PanelCard } from "@/components/ui";
import { api, PatchCandidate, VerificationReport } from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import type { InspectorData } from "@/lib/useShell";
import { AuthGate } from "@/components/AuthGate";
import { readDeepLink } from "@/holographic";
import { Check, XCircle, Wrench, Package, Download, ArrowLeft, Loader2 } from "lucide-react";

function PatchForgeContent() {
  // `useSearchParams` sits with the top-level hooks: calling it after an
  // early return would change the hook count between renders and throw
  // "Rendered more hooks than during the previous render".
  const searchParams = useSearchParams();
  const deepLink = readDeepLink(searchParams);
  const { incidentId, setIncidentId, judgeMode, engineerMode } = useActiveIncident();
  const { openInspector, setIncidentContext } = useShell();

  // A link from the reconstruction view names the incident it belongs to.
  // localStorage is same-tab only, so without this a pasted or bookmarked link
  // would open on whatever incident this browser last viewed.
  useEffect(() => {
    if (deepLink.incidentId && deepLink.incidentId !== incidentId) {
      setIncidentId(deepLink.incidentId);
    }
  }, [deepLink.incidentId, incidentId, setIncidentId]);

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Patch Forge",
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
  const [patches, setPatches] = useState<PatchCandidate[]>([]);
  const [reports, setReports] = useState<VerificationReport[]>([]);

  // Load patches from backend
  const loadPatches = async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getPatches(id);
      if (res && res.patch_candidates) {
        setPatches(res.patch_candidates);
        if (res.verification_reports) {
          setReports(res.verification_reports);
        }
      } else {
        setPatches([]);
        setReports([]);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load patches");
      setPatches([]);
      setReports([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (incidentId) {
      loadPatches(incidentId);
    }
  }, [incidentId]);

  // Open the deep-linked patch once the list has loaded.
  //
  // `?patch=` names a PatchCandidate id, which is what this page keys on, so
  // this is a real selection. `?component=` is not: a PatchCandidate carries
  // `affected_files` — file paths — not component ids, so the component can
  // only be context, and the banner below says as much.
  useEffect(() => {
    const wanted = deepLink.patchId;
    if (!wanted || patches.length === 0) return;
    const match = patches.find((p) => (p.candidate_id || p.id) === wanted);
    if (match) handleOpenPatchInspector(match);
    // `handleOpenPatchInspector` is redefined every render, so it is
    // deliberately not a dependency — including it would re-open the
    // inspector on every keystroke elsewhere on the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLink.patchId, patches]);

  // 9-Point Invariant Verification Checklist Definition
  const INVARIANT_CHECKS = [
    { id: 1, title: "Applies Cleanly to Target Space", description: "Patch applies without conflicts to the target repository state" },
    { id: 2, title: "Regression Test Fails Before Patch", description: "A failing test exists that reproduces the original incident" },
    { id: 3, title: "Regression Test Passes After Patch", description: "The regression test passes after the patch is applied" },
    { id: 4, title: "Original Failure Not Reproduced (0% fails)", description: "The original failure scenario no longer occurs in simulation" },
    { id: 5, title: "Existing System Test Suite Passes", description: "All pre-existing tests continue to pass after the patch" },
    { id: 6, title: "Safety Invariant Budget Maintained", description: "Total latency remains within budget (106ms <= 120ms freshness)" },
    { id: 7, title: "Performance Within Compute Allocation", description: "GPU/CPU utilization stays within allocated thresholds" },
    { id: 8, title: "Forbidden Change Scan Passed", description: "No secrets, credentials, or safety bypasses introduced" },
    { id: 9, title: "Reversible Zero-Impact Rollback Confirmed", description: "Patch can be cleanly reverted without side effects" },
  ];

  // Generate annotated source view (before/after comparison) - returns JSX
  const generateAnnotatedSource = (patch: PatchCandidate) => {
    const lines = (patch.unified_diff || patch.diff || "").split("\n");
    if (lines.length === 0) return <span className="text-[var(--color-fg-muted)]">No diff available</span>;

    return (
      <>
        {lines.map((line, i) => (
          <div key={i} className={`whitespace-pre-wrap ${
            line.startsWith("-") ? "text-[var(--color-danger-fg)]" :
            line.startsWith("+") ? "text-[var(--color-success-fg)]" :
            line.startsWith("@@") ? "text-[var(--color-accent-fg)]" :
            line.startsWith("---") || line.startsWith("+++") ? "text-[var(--color-warning-fg)]" :
            "text-[var(--color-fg-default)]"
          }`}>
            {line}
          </div>
        ))}
      </>
    );
  };

  const activePatches = patches;
  const verifiedCount = activePatches.filter(p => p.verified).length;
  const [selectedPatch, setSelectedPatch] = useState<PatchCandidate | null>(null);

  useEffect(() => {
    if (activePatches.length > 0 && !selectedPatch) {
      setSelectedPatch(activePatches[0]);
    } else if (activePatches.length === 0) {
      setSelectedPatch(null);
    }
  }, [activePatches, selectedPatch]);

  const reportByPatch = useMemo(() => {
    const map = new Map<string, VerificationReport>();
    for (const r of reports) {
      if (r.patch_candidate_id) {
        map.set(r.patch_candidate_id, r);
      }
    }
    return map;
  }, [reports]);
  const paneRefs = useRef<(HTMLPreElement | HTMLDivElement | null)[]>([null, null, null]);

  const handleScroll = (index: number, e: React.UIEvent<HTMLPreElement | HTMLDivElement>) => {
    const target = e.currentTarget as HTMLPreElement | HTMLDivElement;
    const { scrollTop, scrollLeft } = target;

    // Sync to other panes
    paneRefs.current.forEach((ref: HTMLPreElement | HTMLDivElement | null, i: number) => {
      if (ref && i !== index) {
        ref.scrollTop = scrollTop;
        ref.scrollLeft = scrollLeft;
      }
    });
  };

  // Generate candidates
  const handleGenerateCandidates = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Generating patch candidates from digital twin experiment branches...", "info");
      await api.reconstruct(incidentId);
      await loadPatches(incidentId);
      notify("Candidate patches generated and verified against 9-point invariant checklist!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to generate candidates", "error");
    } finally {
      setLoading(false);
    }
  };

  // Create patch package
  const handleCreatePatchPackage = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Assembling verified patch package and regression test suite...", "info");
      await api.exportPatch(incidentId, "zip");
      notify("Patch package created successfully at report/CAU-0001/patch-package (includes fix.patch, apply_patch.py, rollback.sh, PULL_REQUEST.md)!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to create patch package", "error");
    } finally {
      setLoading(false);
    }
  };

  // Open inspector for patch candidate
  const handleOpenPatchInspector = (patch: PatchCandidate) => {
    setSelectedPatch(patch);
    const data: InspectorData = {
      mode: "patch",
      patchId: patch.candidate_id || patch.id,
      patchData: {
        ...patch,
        type: "Code Fix",
        confidence: patch.score * 100,
        limitations: patch.verified
          ? ["Limited to simulated verification", "No production deployment data"]
          : ["Failed one or more invariant gates", "Cannot be safely deployed"],
      },
    };
    openInspector("patch", data);
  };

  // Download verified patch
  const handleDownloadPatch = async () => {
    setLoading(true);
    setError(null);
    try {
      notify("Preparing download for verified patch package...", "info");
      const blob = await api.downloadPatchPackage(incidentId);

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `cauveris-verified-patch-${incidentId.slice(0, 8)}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      notify("Verified patch package ZIP downloaded successfully!", "success");
    } catch (e: any) {
      setError(e.message);
      notify(e.message || "Failed to download patch", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full space-y-5">
      {/* Header */}
      <PageHeader
        title="Patch Forge"
        subtitle="Automated patch candidate synthesis & 9-point invariant gate verification"
        badge={
          <Badge tone="success" dot={true}>
            {verifiedCount} Verified Patch Ready
          </Badge>
        }
      />

      {/*
        Arriving from the reconstruction view. `?component=` is context only: a
        PatchCandidate carries `affected_files` — file paths — and no component
        id, so nothing here can be selected by it. `?patch=`, when present, is a
        real selection and has already been opened by the effect above.
      */}
      {deepLink.componentId && (
        <div
          role="status"
          className="flex flex-wrap items-start gap-3 rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] px-4 py-3 text-xs"
        >
          <Wrench className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-fg-muted)]" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-[var(--color-fg-default)]">
              Opened for component{" "}
              <span className="font-mono">{deepLink.componentId}</span>
            </p>
            <p className="mt-0.5 leading-relaxed text-[var(--color-fg-muted)]">
              Patch candidates are keyed by the files they touch, not by
              component id, so none has been preselected on this component&apos;s
              behalf. Read it as the component the patches below are meant to
              remediate and confirm that against{" "}
              <span className="font-mono">affected_files</span>.
            </p>
          </div>
          <a
            href="/holographic-reconstruction"
            className="inline-flex shrink-0 items-center gap-1.5 rounded-[var(--radius-sm)] border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-fg-default)] transition hover:bg-[var(--color-canvas-subtle)]"
          >
            <ArrowLeft className="h-3 w-3" />
            Back to reconstruction
          </a>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-[var(--color-danger-muted)] border border-[var(--color-danger-muted)]/30 rounded-[var(--radius-md)] text-[var(--color-danger-fg)] text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-[var(--color-danger-fg)] hover:text-[var(--color-fg-default)] text-xs font-semibold uppercase">Dismiss</button>
        </div>
      )}

      {/* Main Content - Three Pane Layout */}
      <PanelStack space="md">
        {/* Panes Header */}
        <Panel title="Patch Candidate List" subtitle={activePatches.length > 0 ? `${activePatches.length} candidates synthesized${verifiedCount > 0 ? ` • ${verifiedCount} verified` : ""}` : "No candidates generated yet"}>
          <PanelSection>
          <div className="space-y-3">
            {activePatches.map((patch, idx) => (
              <PanelCard
                key={patch.candidate_id || patch.id || idx}
                title={patch.title || patch.candidate_id}
                subtitle={
                  <div className="flex items-center gap-3 text-xs text-[var(--color-fg-muted)]">
                    <span>Score: <strong className="font-mono text-[var(--color-fg-default)]">{patch.score}</strong></span>
                    <span>•</span>
                    <span>Files: <strong className="font-mono text-[var(--color-fg-default)]">{patch.affected_files?.join(", ") || "1 file"}</strong></span>
                    <span>•</span>
                    <span>Lines: <strong className="font-mono text-[var(--color-fg-default)]">±{patch.lines_changed || 1}</strong></span>
                  </div>
                }
                trailing={
                  <Badge tone={patch.verified ? "success" : "danger"} dot={true}>
                    {patch.verified ? "VERIFIED" : "REJECTED"}
                  </Badge>
                }
                hoverable
                selected={selectedPatch?.candidate_id === patch.candidate_id}
                onClick={() => handleOpenPatchInspector(patch)}
              >
                <div className="mt-2 flex items-center gap-2 text-[10px] text-[var(--color-fg-muted)]">
                  <span className="font-mono text-xs px-2 py-0.5 rounded bg-[var(--color-canvas)]/40">Unified Diff Available</span>
                  {patch.verified && <span className="text-[var(--color-success-fg)] font-bold">✓ 9/9 Gates</span>}
                </div>
              </PanelCard>
            ))}
            {activePatches.length === 0 && (
              <div className="p-8 text-center text-[var(--color-fg-muted)]">
                <span>No patch candidates generated yet. Click "Generate Candidates" to start.</span>
              </div>
            )}
          </div>
        </PanelSection>
      </Panel>

      <PanelDivider label="Three-Pane Diff View" />

        {/* Three Synchronized Pane Panels */}
        <Panel title="Synchronized Patch Review Panes" subtitle="Unified Diff • Annotated Source • Invariants Checklist">
          {selectedPatch ? (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Pane 1: Unified Diff */}
              <PanelSection title="Universal Unified Diff">
                <div className="relative">
                  <span className="text-[10px] uppercase font-bold text-[var(--color-fg-muted)] tracking-wider block mb-2">
                    {selectedPatch.affected_files?.[0] || "config/inference.yaml"}
                  </span>
                  <pre
                    ref={(el) => { paneRefs.current[0] = el; }}
                    onScroll={(e) => handleScroll(0, e)}
                    className="p-3 h-96 max-h-96 rounded-[var(--radius-md)] bg-[var(--color-canvas)]/60 border border-[var(--color-border-default)] text-xs font-mono text-[var(--color-fg-default)] overflow-auto leading-relaxed whitespace-pre-wrap"
                  >
                    {selectedPatch.unified_diff || selectedPatch.diff || "No diff available"}
                  </pre>
                </div>
              </PanelSection>

              {/* Pane 2: Annotated Source */}
              <PanelSection title="Annotated Source (Before/After)">
                <div className="relative">
                  <span className="text-[10px] uppercase font-bold text-[var(--color-fg-muted)] tracking-wider block mb-2">
                    {selectedPatch.affected_files?.[0] || "config/inference.yaml"} - Annotated
                  </span>
                  <div
                    ref={(el) => { paneRefs.current[1] = el; }}
                    onScroll={(e) => handleScroll(1, e)}
                    className="p-3 h-96 max-h-96 rounded-[var(--radius-md)] bg-[var(--color-canvas)]/60 border border-[var(--color-border-default)] text-xs font-mono text-[var(--color-fg-default)] overflow-auto leading-relaxed whitespace-pre-wrap font-mono"
                  >
                    {generateAnnotatedSource(selectedPatch)}
                  </div>
                </div>
              </PanelSection>

              {/* Pane 3: Invariants Checklist */}
              <PanelSection title="9-Point Invariant Verification Checklist">
                <div
                  ref={(el) => { paneRefs.current[2] = el; }}
                  onScroll={(e) => handleScroll(2, e)}
                  className="h-96 max-h-96 overflow-auto"
                >
                  {(() => {
                    const rep = reportByPatch.get(selectedPatch.candidate_id || selectedPatch.id);
                    const gateResults: Record<number, boolean> = {
                      1: Boolean(rep?.applies_cleanly ?? selectedPatch.applied_cleanly ?? (selectedPatch as any).applies_cleanly ?? false),
                      2: Boolean(rep?.regression_test_fails_before ?? selectedPatch.regression_test_fails_before ?? false),
                      3: Boolean(rep?.regression_test_passes_after ?? selectedPatch.regression_test_passes_after ?? false),
                      4: Boolean(rep?.original_failure_not_reproduced ?? selectedPatch.original_failure_not_reproduced ?? false),
                      5: Boolean(rep?.existing_tests_pass ?? selectedPatch.existing_tests_pass ?? false),
                      6: Boolean(rep?.safety_invariants_pass ?? selectedPatch.safety_invariants_pass ?? false),
                      7: Boolean(rep?.performance_within_budget ?? selectedPatch.performance_within_budget ?? false),
                      8: Boolean(rep?.forbidden_change_scan_passes ?? selectedPatch.forbidden_change_scan_passes ?? false),
                      9: Boolean(rep?.rollback_test_passes ?? selectedPatch.rollback_test_passes ?? false),
                    };

                    return (
                      <div className="space-y-3">
                        {INVARIANT_CHECKS.map((check, i) => {
                          const passed = Boolean(gateResults[check.id]);
                          return (
                            <div
                              key={i}
                              className={`flex items-start gap-3 p-3 rounded-[var(--radius-sm)] ${
                                passed
                                  ? "bg-[var(--color-success-muted)]/10 border border-[var(--color-success-muted)]/20"
                                  : "bg-[var(--color-danger-muted)]/10 border border-[var(--color-danger-muted)]/20"
                              }`}
                            >
                              {passed ? (
                                <Check className="h-5 w-5 text-[var(--color-success-fg)] flex-shrink-0 mt-0.5" />
                              ) : (
                                <XCircle className="h-5 w-5 text-[var(--color-danger-fg)] flex-shrink-0 mt-0.5" />
                              )}
                              <div>
                                <div className="font-medium text-sm text-[var(--color-fg-default)]">{check.title}</div>
                                <div className="text-xs text-[var(--color-fg-muted)] mt-0.5">{check.description}</div>
                                <div className="flex items-center gap-2 mt-2">
                                  <span
                                    className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                      passed
                                        ? "text-[var(--color-success-fg)] bg-[var(--color-success-muted)]/20"
                                        : "text-[var(--color-danger-fg)] bg-[var(--color-danger-muted)]/20"
                                    }`}
                                  >
                                    {passed ? "PASS" : "FAIL"}
                                  </span>
                                  <span className="text-xs text-[var(--color-fg-muted)]">Gate {i + 1} / 9</span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    );
                  })()}
                </div>
              </PanelSection>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {[1, 2, 3].map((i) => (
                <PanelSection key={i} title={`Pane ${i}: ${["Universal Unified Diff", "Annotated Source", "9-Point Invariant Verification Checklist"][i - 1]}`}>
                  <div className="h-96 max-h-96 flex items-center justify-center text-[var(--color-fg-muted)] text-sm">
                    Select a patch candidate to view diff
                  </div>
                </PanelSection>
              ))}
            </div>
          )}
        </Panel>

        <PanelDivider label="Verification Controls" />

        {/* Summary & Actions */}
        <Panel title="Verification Controls & Summary" subtitle="Candidate statistics and patch package operations">
          <div className="space-y-5">
            {/* Summary Stats */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Stat label="Total Generated" value={activePatches.length} sub="Experiment branches" trend="flat" />
              <Stat label="Verified" value={verifiedCount} sub="Passed 9/9 gates" trend="success" />
              <Stat label="Rejected" value={activePatches.length - verifiedCount} sub="Failed safety gates" trend="danger" />
              <Stat label="Top Score" value={activePatches.length > 0 ? activePatches[0].score : "0.97"} sub={activePatches.length > 0 ? activePatches[0].candidate_id : "patch-exp-h1"} trend="success" />
            </div>

            {/* Action Buttons */}
            <div className="pt-1">
              <div className="flex flex-wrap items-center gap-3">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleGenerateCandidates}
                  disabled={loading}
                  aria-label="Generate new candidates"
                  className="h-8 px-3.5 text-xs font-medium"
                >
                  <Wrench className="h-3.5 w-3.5" />
                  <span>{loading ? "Synthesizing..." : "Generate Candidates"}</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCreatePatchPackage}
                  disabled={loading}
                  aria-label="Create patch package"
                  className="h-8 px-3.5 text-xs font-medium"
                >
                  <Package className="h-3.5 w-3.5" />
                  <span>{loading ? "Assembling..." : "Create Package"}</span>
                </Button>
                <Button
                  variant="success"
                  size="sm"
                  onClick={handleDownloadPatch}
                  disabled={loading}
                  aria-label="Download verified patch"
                  className="h-8 px-3.5 text-xs font-medium"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>{loading ? "Downloading..." : "Download Verified Patch"}</span>
                </Button>
              </div>
            </div>

            <div className="p-3 rounded-[var(--radius-lg)] bg-[var(--color-canvas-subtle)]/50 border border-[var(--color-border-default)] text-xs text-[var(--color-fg-muted)] leading-relaxed">
              The verified patch package includes zero-dependency executable <code className="text-[var(--color-accent-fg)] font-mono">apply_patch.py</code>, standard universal unified diff <code className="text-[var(--color-accent-fg)] font-mono">fix.patch</code>, safety rollback script, and automated reviewer verification checklist.
            </div>
          </div>
        </Panel>
      </PanelStack>
    </div>
  );
}

/**
 * `useSearchParams` opts this tree into client-side rendering, which a
 * statically prerendered route rejects at build time unless the nearest
 * boundary above it is a Suspense. The inner component keeps the hook on the
 * client side of that boundary.
 */
export default function PatchForge() {
  return (
    <AuthGate redirect="/patch-forge" loadingLabel="Loading Patch Forge...">
      <Suspense
        fallback={
          <div className="min-h-screen flex items-center justify-center bg-[var(--color-canvas)] p-4">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)]" />
          </div>
        }
      >
        <PatchForgeContent />
      </Suspense>
    </AuthGate>
  );
}