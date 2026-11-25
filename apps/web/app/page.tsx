"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  X,
  Divide,
  AlertTriangle,
  HelpCircle,
  Play,
  Square,
  RotateCcw,
  CheckCircle,
  Scale,
  Wrench,
  Zap,
  Search,
  Trash2,
  Info,
  Loader2,
  Server,
  FolderOpen,
  ArrowRight,
  ShieldCheck,
  Activity,
  Layers,
  Globe,
  Download,
} from "lucide-react";
import {
  Button,
  Badge,
  EmptyState,
  PageHeader,
  Toolbar,
  ToolbarGroup,
  ToolbarItem,
  ToolbarSeparator,
  ToolbarTitle,
  ToolbarSpacer,
} from "@/components/ui";
import { Dialog, ConfirmDialog } from "@/components/ui/Dialog";
import { Table, type Column } from "@/components/ui/Table";
import { AuthGate } from "@/components/AuthGate";
import { SessionExportDialog } from "@/components/workspace/SessionExportDialog";
import {
  api,
  Incident,
  PipelineStageInfo,
  PipelineEventsResponse,
  EvidenceValidationSummary,
  SystemHealthResponse,
  ModelProviderHealthResponse,
} from "@/lib/api";
import { notify } from "@/components/Notification";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell, buildIncidentContext } from "@/lib/useShell";
import {
  InstrumentPanel,
  SignalTag,
  TraceValue,
  StageRail,
  CapabilityMap,
  SystemPulse,
  CapabilityItem,
  StageStep,
} from "@/design-system";

interface ActionableError {
  title: string;
  message: string;
  type: "backend" | "model" | "upload" | "validation" | "pipeline" | "stale" | "cancellation" | "duplicate";
  actionLabel?: string;
  onAction?: () => void;
}

export default function MissionControl() {
  return (
    <AuthGate redirect="/workspace" loadingLabel="Initializing Systems Workbench...">
      <MissionControlContent />
    </AuthGate>
  );
}

function MissionControlContent() {
  const { incidentId, setIncidentId, judgeMode, setJudgeMode, engineerMode, setEngineerMode } = useActiveIncident();
  const { setIncidentContext, openInspector, setWorkspacePrompt } = useShell();
  const router = useRouter();

  // Primary data state
  const [incidentData, setIncidentData] = useState<Incident | null>(null);
  const [reportData, setReportData] = useState<any>(null);
  const [availableIncidents, setAvailableIncidents] = useState<Incident[]>([]);
  const [evidenceSummary, setEvidenceSummary] = useState<EvidenceValidationSummary | null>(null);

  // System & Provider Health
  const [backendOnline, setBackendOnline] = useState<boolean>(true);
  const [backendLatency, setBackendLatency] = useState<number | null>(null);
  const [modelProviderOnline, setModelProviderOnline] = useState<boolean>(true);
  const [modelProviderName, setModelProviderName] = useState<string>("LOCAL_DETERMINISTIC_ONLY");
  // Populated from /model-health on load; empty means "not reported yet".
  const [modelId, setModelId] = useState<string>("");
  const [circuitBreakerState, setCircuitBreakerState] = useState<string>("CLOSED");
  const [dailyBudgetUsed, setDailyBudgetUsed] = useState<number>(0.0);
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);

  // Pipeline progression state
  const [isSessionExportOpen, setIsSessionExportOpen] = useState<boolean>(false);
  const [pipelineState, setPipelineState] = useState<string>("IDLE");
  const [pipelineProgress, setPipelineProgress] = useState<number>(0);
  const [activeStageId, setActiveStageId] = useState<string | null>(null);
  const [pipelineStages, setPipelineStages] = useState<PipelineStageInfo[]>([]);
  const [isDemonstration, setIsDemonstration] = useState<boolean>(false);

  // Action / operation loading flags
  const [loading, setLoading] = useState<boolean>(false);
  const [isStarting, setIsStarting] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [isResetting, setIsResetting] = useState<boolean>(false);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  // Actionable errors
  const [actionableError, setActionableError] = useState<ActionableError | null>(null);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Health check
  const checkHealth = useCallback(async () => {
    const t0 = performance.now();
    let backendError = false;
    try {
      const res: SystemHealthResponse = await api.health();
      const t1 = performance.now();
      setBackendOnline(res?.status === "healthy");
      setBackendLatency(Math.round(t1 - t0));
      setIsReconnecting(false);
    } catch {
      backendError = true;
      setBackendOnline(false);
      setBackendLatency(null);
      setIsReconnecting(false);
    }

    try {
      const modelRes: any = await api.modelHealth();
      setModelProviderOnline(modelRes?.status === "healthy");
      const providerState =
        modelRes?.provider_state ||
        (modelRes?.nebius_configured ? "NEBIUS_NVIDIA_ACTIVE" : "LOCAL_DETERMINISTIC_ONLY");
      setModelProviderName(providerState);
      if (modelRes?.model_id || modelRes?.exact_model_id) {
        setModelId(modelRes.model_id || modelRes.exact_model_id);
      }
      if (modelRes?.circuit_breaker?.circuit_state) {
        setCircuitBreakerState(modelRes.circuit_breaker.circuit_state);
      }
      if (typeof modelRes?.circuit_breaker?.daily_budget_used === "number") {
        setDailyBudgetUsed(modelRes.circuit_breaker.daily_budget_used);
      }
    } catch {
      setModelProviderOnline(true);
      setModelProviderName("LOCAL_DETERMINISTIC_ONLY");
    }

    if (backendError) {
      setActionableError((prev) => {
        if (prev?.type === "backend") return prev;
        return {
          title: "Cauveris Backend Connection Failed",
          message: "UNAVAILABLE: Cannot communicate with Cauveris API at port 8000. Ensure the FastAPI backend server is active.",
          type: "backend",
          actionLabel: "Retry Connection",
          onAction: checkHealth,
        };
      });
    } else {
      setActionableError((prev) => (prev?.type === "backend" ? null : prev));
    }
  }, []);

  const loadIncidentsList = useCallback(async () => {
    try {
      const list = await api.list();
      const incidentsList = Array.isArray(list)
        ? list
        : (list as any)?.incidents && Array.isArray((list as any).incidents)
        ? (list as any).incidents
        : [];
      setAvailableIncidents(incidentsList);
    } catch {
      setAvailableIncidents([]);
    }
  }, []);

  const loadIncidentDetails = useCallback(
    async (id: string | null) => {
      if (!id) {
        setIncidentData(null);
        setReportData(null);
        setEvidenceSummary(null);
        setPipelineStages([]);
        setPipelineState("IDLE");
        setPipelineProgress(0);
        setActiveStageId(null);
        setIsDemonstration(false);
        return;
      }

      setLoading(true);
      setActionableError(null);
      try {
        const inc = await api.get(id);
        setIncidentData(inc);
        setIsDemonstration(Boolean(inc.is_demonstration));

        try {
          const events = await api.getEvents(id);
          if (events) {
            setPipelineState(events.state || "IDLE");
            setPipelineProgress(Math.round((events.progress || 0) * 100));
            setActiveStageId(events.active_stage_id || null);
            if (events.stages) {
              setPipelineStages(events.stages);
            }
          }
        } catch {
          // ignore
        }

        try {
          const val = await api.validateEvidence(id);
          setEvidenceSummary(val);
        } catch {
          // ignore
        }

        try {
          const rep = await api.getReport(id);
          setReportData(rep);
        } catch {
          setReportData(null);
        }
      } catch (err: any) {
        setActionableError({
          title: "Failed to Load Incident Details",
          message: err.message || `Could not fetch incident ${id}`,
          type: "backend",
          actionLabel: "Retry",
          onAction: () => loadIncidentDetails(id),
        });
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    checkHealth();
    loadIncidentsList();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, [checkHealth, loadIncidentsList]);

  const routerRef = useRef(router);
  routerRef.current = router;

  useEffect(() => {
    if (incidentId) {
      loadIncidentDetails(incidentId);
    } else {
      loadIncidentDetails(null);
      // If no active incident is open, route to workspace launcher to pick or create one
      const stored = typeof window !== "undefined" ? localStorage.getItem("cauveris_active_incident_id") : null;
      if (!stored) {
        if (typeof routerRef.current?.replace === "function") {
          routerRef.current.replace("/workspace");
        } else if (typeof routerRef.current?.push === "function") {
          routerRef.current.push("/workspace");
        }
      }
    }
  }, [incidentId, loadIncidentDetails]);

  // Sync pipeline state if started or stopped from TopContextBar while on Overview
  useEffect(() => {
    const onPipelineState = (e: Event) => {
      const detail = (e as CustomEvent<{ incidentId: string; state: string }>).detail;
      if (detail && detail.incidentId === incidentId) {
        setPipelineState(detail.state);
        if (detail.state === "RUNNING") {
          setIsStarting(true);
          setPipelineProgress(5);
        } else {
          setIsStarting(false);
        }
      }
    };
    window.addEventListener("cauveris:pipeline-state", onPipelineState);
    return () => window.removeEventListener("cauveris:pipeline-state", onPipelineState);
  }, [incidentId]);

  // Sync shell topbar
  useEffect(() => {
    if (incidentData) {
      const ctx = buildIncidentContext(
        incidentData,
        pipelineState,
        activeStageId,
        pipelineStages,
        evidenceSummary,
        modelProviderName,
        backendOnline,
        judgeMode,
        engineerMode
      );
      setIncidentContext(ctx);
    } else if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: "Loading...",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 0,
        modelProvider: modelProviderName,
        backendStatus: backendOnline ? "online" : "offline",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [
    incidentData,
    pipelineState,
    activeStageId,
    pipelineStages,
    evidenceSummary,
    modelProviderName,
    backendOnline,
    judgeMode,
    engineerMode,
    incidentId,
    setIncidentContext,
  ]);

  // Real-time polling
  useEffect(() => {
    if (pipelineState === "RUNNING" && incidentId) {
      pollingRef.current = setInterval(async () => {
        try {
          const events: PipelineEventsResponse = await api.getEvents(incidentId);
          if (events) {
            setPipelineState(events.state);
            setPipelineProgress(Math.round((events.progress || 0) * 100));
            setActiveStageId(events.active_stage_id || null);
            if (events.stages) {
              setPipelineStages(events.stages);
            }

            if (events.state === "SUCCESS" || events.state === "COMPLETED") {
              if (pollingRef.current) clearInterval(pollingRef.current);
              setIsStarting(false);
              notify("Investigation pipeline completed successfully! Verified patch generated.", "success");
              await loadIncidentDetails(incidentId);
            } else if (events.state === "DEGRADED" || events.state === "PARTIAL") {
              if (pollingRef.current) clearInterval(pollingRef.current);
              setIsStarting(false);
              notify("Pipeline finished with degraded warnings. Review invariant checklist.", "warning");
              await loadIncidentDetails(incidentId);
            } else if (events.state === "FAILED") {
              if (pollingRef.current) clearInterval(pollingRef.current);
              setIsStarting(false);
              setActionableError({
                title: "Investigation Pipeline Failed",
                message: events.error || "A required pipeline stage failed and halted execution.",
                type: "pipeline",
                actionLabel: "Reset & Rerun",
                onAction: () => handleResetDemo(),
              });
              await loadIncidentDetails(incidentId);
            } else if (events.state === "CANCELLED") {
              if (pollingRef.current) clearInterval(pollingRef.current);
              setIsStarting(false);
              setIsCancelling(false);
              notify("Investigation cancelled by operator.", "info");
              await loadIncidentDetails(incidentId);
            }
          }
        } catch {
          setIsReconnecting(true);
        }
      }, 750);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [pipelineState, incidentId, loadIncidentDetails]);

  // Handlers
  const handleStartInvestigation = async () => {
    if (!incidentId) return;
    if (isStarting || pipelineState === "RUNNING") {
      notify("Investigation is already currently executing.", "warning");
      return;
    }
    setIsStarting(true);
    setActionableError(null);
    try {
      notify("Starting autonomous reality debugging pipeline...", "info");
      await api.reconstruct(incidentId);
      setPipelineState("RUNNING");
      setPipelineProgress(5);
    } catch (e: any) {
      setIsStarting(false);
      setActionableError({
        title: "Investigation Start Failed",
        message: e.message || "Failed to launch pipeline reconstruction on backend.",
        type: "pipeline",
        actionLabel: "Retry Start",
        onAction: () => handleStartInvestigation(),
      });
      notify(e.message || "Start failed", "error");
    }
  };

  const handleCancelInvestigation = async () => {
    if (!incidentId) return;
    setIsCancelling(true);
    try {
      await api.cancel(incidentId);
      setPipelineState("CANCELLED");
      setIsStarting(false);
      setActionableError({
        title: "Investigation Cancelled",
        message: "Pipeline halted by user. Active stage was cancelled and remaining stages skipped.",
        type: "cancellation",
        actionLabel: "Reset & Rerun",
        onAction: () => handleResetDemo(),
      });
      notify("Cancellation signal dispatched.", "info");
      await loadIncidentDetails(incidentId);
    } catch (e: any) {
      notify(e.message || "Cancellation failed", "error");
    } finally {
      setIsCancelling(false);
    }
  };

  const handleResetDemo = async () => {
    if (!incidentId) return;
    setIsResetting(true);
    setActionableError(null);
    try {
      await api.reset(incidentId);
      setPipelineState("IDLE");
      setPipelineProgress(0);
      setActiveStageId(null);
      setReportData(null);
      await loadIncidentsList();
      await loadIncidentDetails(incidentId);
      notify("Demo state reset to ready. Ready for rerun.", "success");
    } catch (e: any) {
      notify(e.message || "Reset failed", "error");
    } finally {
      setIsResetting(false);
    }
  };

  const handleValidateEvidence = async () => {
    if (!incidentId) return;
    setIsValidating(true);
    try {
      const summary = await api.validateEvidence(incidentId);
      setEvidenceSummary(summary);
      notify(`Validation complete: ${summary.evidence_count} items analyzed`, summary.is_valid ? "success" : "warning");
    } catch (e: any) {
      notify(e.message || "Validation failed", "error");
    } finally {
      setIsValidating(false);
    }
  };

  const isPipelineActive = pipelineState === "RUNNING";

  // Transformed StageRail format
  const stageRailSteps: StageStep[] = useMemo(() => {
    if (pipelineStages.length === 0) return [];
    return pipelineStages.map((s) => ({
      id: s.id,
      name: s.name,
      status:
        s.status === "SUCCESS"
          ? "COMPLETED"
          : s.status === "FAILED"
          ? "FAILED"
          : s.status === "RUNNING"
          ? "RUNNING"
          : s.status === "DEGRADED"
          ? "PARTIAL"
          : s.status === "SKIPPED"
          ? "BLOCKED"
          : "PENDING",
      durationMs: s.duration_ms ?? undefined,
      blockedReason: s.error || undefined,
      warnings: s.status === "DEGRADED" ? ["Degraded metrics"] : undefined,
    }));
  }, [pipelineStages]);

  // Transformed Capability Map
  // Every capability is derived from what the backend actually produced for
  // this incident — nothing is marked capable just because the page is open.
  const capabilities: CapabilityItem[] = useMemo(() => {
    const capRep = reportData?.capability_report;
    const evidenceCount = evidenceSummary?.evidence_count ?? incidentData?.evidence_count ?? 0;
    const hypCount = reportData?.hypotheses?.length ?? 0;
    const expCount = reportData?.experiments?.length ?? 0;
    const patchCount = reportData?.patch_candidates?.length ?? 0;
    const verCount = reportData?.verification_reports?.length ?? 0;
    const verified = (reportData?.verification_reports ?? []).some((v: any) => v?.verified);
    return [
      { key: "ingestion", name: "Ingestion", capable: evidenceCount > 0 },
      { key: "extraction", name: "Extraction", capable: evidenceCount > 0 },
      { key: "diagnosis", name: "Diagnosis", capable: capRep ? capRep.diagnosis?.capable !== false : hypCount > 0 },
      { key: "simulation", name: "Simulation", capable: capRep ? capRep.simulation?.capable !== false : expCount > 0 },
      { key: "repair", name: "Repair Forge", capable: capRep ? capRep.repair?.capable !== false : patchCount > 0 },
      { key: "editing", name: "Config Patch", capable: capRep ? (capRep.repair?.editable_controls_count ?? 0) > 0 : patchCount > 0 },
      { key: "verification", name: "Verification", capable: capRep ? capRep.verification?.capable !== false : verCount > 0 },
      { key: "export", name: "Package Export", capable: verified },
    ];
  }, [reportData, evidenceSummary, incidentData]);

  // Incident columns for recent investigations
  const incidentColumns: Column<Incident>[] = useMemo(
    () => [
      {
        key: "id",
        header: "Incident ID",
        width: "120px",
        render: (row: Incident) => (
          <span className="font-mono text-xs font-semibold text-[var(--color-fg-default,#1f2933)]">
            {row.id}
          </span>
        ),
      },
      {
        key: "title",
        header: "Title & Scope",
        render: (row: Incident) => (
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-[var(--text-primary,#f4f4f5)] truncate">
              {row.title || `Incident ${row.id}`}
            </span>
            {row.is_demonstration && (
              <SignalTag signal="SAMPLE DATA" size="xs" geometry="instrument-box" />
            )}
          </div>
        ),
      },
      {
        key: "system_name",
        header: "Target System",
        width: "150px",
        render: (row: Incident) => (
          <span className="text-xs font-mono text-[var(--text-secondary,#a1a1aa)]">
            {row.system_name || "embedded"}
          </span>
        ),
      },
      {
        key: "evidence_count",
        header: "Evidence",
        width: "110px",
        align: "right",
        render: (row: Incident) => (
          <span className="text-xs font-mono tabular-nums text-[var(--text-secondary,#a1a1aa)]">
            {row.evidence_count} artifacts
          </span>
        ),
      },
      {
        key: "actions",
        header: "",
        width: "90px",
        align: "center",
        render: (row: Incident) => {
          const isActive = row.id === incidentId;
          return isActive ? (
            <span className="text-[10px] px-2 py-0.5 border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] text-zinc-100 font-bold rounded-[var(--radius-sm,4px)]">
              ACTIVE
            </span>
          ) : (
            <button
              onClick={() => {
                setIncidentId(row.id);
                loadIncidentDetails(row.id);
                notify(`Switched active investigation to ${row.id}`, "info");
              }}
              className="text-xs font-mono text-[var(--text-tertiary,#71717a)] hover:text-zinc-100 transition-colors"
            >
              Resume →
            </button>
          );
        },
      },
    ],
    [incidentId, loadIncidentDetails, setIncidentId]
  );

  return (
    <div className="w-full space-y-5">
      {/*
        Standard Page Header.

        The header is incident-scoped: it acts on the incident that is open.
        Creating, uploading and loading the sample benchmark moved to the
        workspace launcher, which owns those actions exactly once — this page
        used to carry a third copy of each.
      */}
      <PageHeader
        title="Overview"
        subtitle="Operational entry point & autonomous reality debugger for robotic systems"
        actionsBelow
        breadcrumbs={[{ label: "Overview" }]}
        badge={
          isDemonstration ? (
            <Badge tone="attention" size="sm">SAMPLE DATA</Badge>
          ) : undefined
        }
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={handleValidateEvidence}
              disabled={!incidentId || isValidating || isPipelineActive}
              leadingIcon={<CheckCircle className="h-3.5 w-3.5" />}
              loading={isValidating}
              loadingText="Validating..."
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Validate Evidence
            </Button>

            {isPipelineActive && (
              <Button
                variant="danger"
                size="sm"
                onClick={handleCancelInvestigation}
                disabled={isCancelling}
                leadingIcon={<Square className="h-3.5 w-3.5 fill-current" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                {isCancelling ? "Cancelling..." : "Cancel"}
              </Button>
            )}

            {!isPipelineActive && (
              <Button
                variant="primary"
                size="sm"
                onClick={handleStartInvestigation}
                disabled={!incidentId || isStarting || !backendOnline}
                leadingIcon={<Play className="h-3.5 w-3.5 fill-current" />}
                loading={isStarting}
                loadingText="Starting..."
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Start
              </Button>
            )}

            {incidentId && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleResetDemo}
                disabled={isResetting || isPipelineActive}
                leadingIcon={<RotateCcw className="h-3.5 w-3.5" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                {isResetting ? "Resetting..." : "Reset"}
              </Button>
            )}

            {incidentId && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsSessionExportOpen(true)}
                disabled={isPipelineActive}
                leadingIcon={<Download className="h-3.5 w-3.5" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Export Session
              </Button>
            )}

            {incidentId && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setWorkspacePrompt(true)}
                leadingIcon={<FolderOpen className="h-3.5 w-3.5" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Switch Workspace
              </Button>
            )}
          </div>
        }
      />

      <SessionExportDialog
        open={isSessionExportOpen}
        onClose={() => setIsSessionExportOpen(false)}
        incidentId={incidentId}
      />

      {/* System Pulse Diagnostic Strip */}
      <SystemPulse
        status={{
          backend: backendOnline ? "online" : "offline",
          backendLatencyMs: backendLatency || undefined,
          worker: isPipelineActive ? "busy" : "idle",
          storage: "healthy",
          nebiusProvider: modelProviderName,
          nebiusModel: modelId,
          circuitBreakerState: circuitBreakerState,
          dailyBudgetUsed: dailyBudgetUsed,
          activeJobsCount: isPipelineActive ? 1 : 0,
        }}
      />

      {/* Actionable Error Display */}
      {actionableError && (
        <div
          className="p-3 bg-rose-50 border border-rose-200 rounded-[var(--radius-md,6px)] dark:bg-rose-950/30 dark:border-rose-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs"
          role="alert"
        >
          <div className="flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 text-[var(--color-fg-subtle,#7b8794)] shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-[var(--color-fg-default,#1f2933)]">{actionableError.title}</p>
              <p className="text-[var(--text-secondary,#a1a1aa)]">{actionableError.message}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-center">
            {actionableError.onAction && (
              <Button
                variant="primary"
                size="sm"
                onClick={actionableError.onAction}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                {actionableError.actionLabel || "Resolve"}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setActionableError(null)}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {/*
        No incident open.

        This used to be a drag-and-drop intake workbench with its own Upload,
        Create and Load Sample buttons — a second copy of three actions that
        also lived in the top bar and in the page header.  Intake now happens
        once, in the workspace launcher, so this page only points there.
      */}
      {!incidentId && (
        <div className="rounded-[var(--radius-lg,8px)] bg-[var(--surface-card,var(--color-canvas-default))] shadow-[var(--elevation-card)]">
          <EmptyState
            icon={<FolderOpen className="h-10 w-10" />}
            title="No workspace open"
            description="Create an incident from an evidence archive, a source repository, or an empty investigation — or resume a session you saved earlier."
            action="Open the workspace"
            actionOnClick={() => router.push("/workspace")}
            size="lg"
          />
        </div>
      )}

      {/* WORKBENCH VIEW 2: INCIDENT OVERVIEW & BRIEFING (Rendered when incident is loaded) */}
      {incidentId && (
        <div className="space-y-4">
          <InstrumentPanel
            title={incidentData?.title || (isDemonstration ? "Sample Demonstration Benchmark" : `Incident ${incidentId}`)}
            subtitle={isDemonstration ? "Explicit Sample Benchmark • Demonstration Target" : `Target System: ${incidentData?.system_name || "UNAVAILABLE"}`}
          >
            <div className="flex items-center justify-between text-xs font-mono text-[var(--text-secondary,#a1a1aa)]">
              <span>Active Target: <span className="text-[var(--text-primary,#f4f4f5)] font-bold">{incidentId}</span></span>
              <span>Status: <span className="text-[var(--color-fg-default,#1f2933)] font-bold">{incidentData?.status || "OBSERVED"}</span></span>
            </div>
          </InstrumentPanel>
          {/* Top Traceable Metrics Strip */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
            <TraceValue
              label="Pipeline State"
              value={pipelineState}
              unit="status"
              provenance="OBSERVED"
              source="State Machine Orchestrator"
              onSelect={() =>
                openInspector("evidence", {
                  mode: "evidence",
                  evidenceId: incidentId,
                  evidenceData: { pipelineState, stagesCount: pipelineStages.length },
                })
              }
            />

            <TraceValue
              label="Artifact Coverage"
              value={evidenceSummary?.evidence_count ?? incidentData?.evidence_count ?? 0}
              unit="files"
              provenance="DECLARED"
              source="Artifact Inventory"
              onSelect={() =>
                openInspector("evidence", {
                  mode: "evidence",
                  evidenceId: incidentId,
                  evidenceData: evidenceSummary || {},
                })
              }
            />

            <TraceValue
              label="Verification Gate"
              value={reportData?.verification_report?.achieved_level ?? "PENDING"}
              unit="level"
              provenance={reportData?.verification_report?.achieved_level ? "VERIFIED" : "PENDING"}
              source="Verification Engine"
              onSelect={() =>
                openInspector("patch", {
                  mode: "patch",
                  patchId: reportData?.selected_repair_id || "repair",
                  patchData: reportData?.verification_report || {},
                })
              }
            />

            <TraceValue
              label="Reconstruction Confidence"
              value={
                reportData?.diagnosis?.confidence != null
                  ? `${Math.round(reportData.diagnosis.confidence * 100)}`
                  : "—"
              }
              unit="%"
              provenance={reportData?.diagnosis?.confidence != null ? "CALIBRATED" : "PENDING"}
              source="Digital Twin Simulator"
              uncertainty={reportData?.diagnosis?.uncertainty ?? undefined}
            />
          </div>

          {/* Capability Map — a decision is only shown when the backend actually produced one */}
          {reportData?.capability_report ? (
            <CapabilityMap
              capabilities={capabilities}
              decision={reportData.capability_report.honest_repair_decision || "PARTIAL"}
              decisionReason={reportData.capability_report.decision_reason || "No decision recorded for this incident"}
            />
          ) : (
            <div className="rounded-[var(--radius-lg,8px)] bg-[var(--surface-card,var(--color-canvas-default))] shadow-[var(--elevation-card)] p-4">
              <div className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
                Capability Map
              </div>
              <p className="mt-1 text-xs text-[var(--color-fg-muted)]">
                No capability evaluation for this incident yet — start the investigation pipeline.
              </p>
            </div>
          )}

          {/* Stage Rail Execution Stepper */}
          {stageRailSteps.length > 0 && (
            <InstrumentPanel
              title="Autonomous Pipeline Execution Rail"
              subtitle="Dependency-gated execution stream with execution timings"
            >
              <StageRail stages={stageRailSteps} currentStageId={activeStageId} />
            </InstrumentPanel>
          )}
        </div>
      )}

      {/* Recent Investigations Ledger */}
      <InstrumentPanel
        title="Incident Directory & Provenance Registry"
        subtitle={`${availableIncidents.length} recorded system investigations`}
      >
        <Table
          columns={incidentColumns}
          data={availableIncidents}
          rowKey={(row) => row.id}
          emptyMessage='No investigations recorded yet. Click "Load Golden Incident" or upload a package.'
          aria-label="Recent investigations"
        />
      </InstrumentPanel>
    </div>
  );
}
