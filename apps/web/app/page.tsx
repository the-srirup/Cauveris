"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Check,
  X,
  Divide,
  AlertTriangle,
  HelpCircle,
  Plus,
  Upload,
  Download,
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
  FileArchive,
  ArrowRight,
  ShieldCheck,
  Activity,
  Layers,
} from "lucide-react";
import {
  Button,
  Badge,
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
    <AuthGate redirect="/" loadingLabel="Initializing Systems Workbench...">
      <MissionControlContent />
    </AuthGate>
  );
}

function MissionControlContent() {
  const { incidentId, setIncidentId, judgeMode, setJudgeMode, engineerMode, setEngineerMode } = useActiveIncident();
  const { setIncidentContext, openInspector } = useShell();

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
  const [modelId, setModelId] = useState<string>("nvidia/Llama-3.1-Nemotron-70B-Instruct-HF");
  const [circuitBreakerState, setCircuitBreakerState] = useState<string>("CLOSED");
  const [dailyBudgetUsed, setDailyBudgetUsed] = useState<number>(0.0);
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);

  // Pipeline progression state
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
  const [isDraggingPackage, setIsDraggingPackage] = useState<boolean>(false);
  const [uploadManifest, setUploadManifest] = useState<{ name: string; size: number } | null>(null);

  // Actionable errors
  const [actionableError, setActionableError] = useState<ActionableError | null>(null);

  // Modals & UI controls
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [showEvidenceDrawer, setShowEvidenceDrawer] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState<string>("");
  const [newSystemName, setNewSystemName] = useState<string>("warehouse-amr-01");
  const [newDescription, setNewDescription] = useState<string>("");

  // Engineer mode interactive simulation state
  const [simBatchWindow, setSimBatchWindow] = useState<number>(100);
  const [simQosDepth, setSimQosDepth] = useState<number>(1);
  const [simClockSkew, setSimClockSkew] = useState<number>(0);
  const [simRunning, setSimRunning] = useState<boolean>(false);
  const [simResult, setSimResult] = useState<any>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
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

  useEffect(() => {
    if (incidentId) {
      loadIncidentDetails(incidentId);
    } else {
      loadIncidentDetails(null);
    }
  }, [incidentId, loadIncidentDetails]);

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
  const handleLoadGolden = async () => {
    setLoading(true);
    setActionableError(null);
    try {
      const res = await api.create(true);
      if (!res.incident_id) {
        throw new Error("Backend did not return an incident ID");
      }
      const newId = res.incident_id;
      setIncidentId(newId);
      setIsDemonstration(true);
      await loadIncidentsList();
      await loadIncidentDetails(newId);
      notify("Golden incident loaded! Real local pipeline ready for investigation.", "success");
    } catch (e: any) {
      setActionableError({
        title: "Failed to Load Golden Incident",
        message: e.message || "Could not initialize golden benchmark incident from backend.",
        type: "backend",
        actionLabel: "Retry",
        onAction: () => handleLoadGolden(),
      });
      notify(e.message || "Failed to load golden incident", "error");
    } finally {
      setLoading(false);
    }
  };

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

  const handleTriggerUpload = () => {
    fileInputRef.current?.click();
  };

  const processUploadFile = async (file: File) => {
    setLoading(true);
    setUploadManifest({ name: file.name, size: file.size });
    try {
      notify(`Uploading incident package: ${file.name}...`, "info");
      const uploadRes = await api.uploadPackage(file);
      const newId = uploadRes.incident_id;
      setIncidentId(newId);
      setIsDemonstration(false);
      await loadIncidentsList();
      await loadIncidentDetails(newId);
      notify(`Package ingested: ${uploadRes.evidence_count} artifacts indexed for ${newId}`, "success");
    } catch (err: any) {
      setUploadManifest(null);
      setActionableError({
        title: "Upload Failed",
        message: "Upload failed. The backend did not accept this package.",
        type: "upload",
        actionLabel: "Try Again",
        onAction: () => handleTriggerUpload(),
      });
      notify("Upload failed. The backend did not accept this package.", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processUploadFile(file);
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
  const capabilities: CapabilityItem[] = useMemo(() => {
    const capRep = reportData?.capability_report;
    return [
      { key: "ingestion", name: "Ingestion", capable: true },
      { key: "extraction", name: "Extraction", capable: (evidenceSummary?.evidence_count ?? 0) > 0 },
      { key: "diagnosis", name: "Diagnosis", capable: capRep ? capRep.diagnosis?.capable !== false : true },
      { key: "simulation", name: "Simulation", capable: capRep ? capRep.simulation?.capable !== false : true },
      { key: "repair", name: "Repair Forge", capable: capRep ? capRep.repair?.capable !== false : true },
      { key: "editing", name: "Config Patch", capable: capRep ? capRep.repair?.editable_controls_count > 0 : true },
      { key: "verification", name: "Verification", capable: capRep ? capRep.verification?.capable !== false : true },
      { key: "export", name: "Package Export", capable: true },
    ];
  }, [reportData, evidenceSummary]);

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
      <input type="file" ref={fileInputRef} onChange={handleFileChange} accept=".zip,.tar.gz" className="hidden" />

      {/* Standard Page Header */}
      <PageHeader
        title="Overview"
        subtitle="Operational entry point & autonomous reality debugger for robotic systems"
        breadcrumbs={[{ label: "Overview" }]}
        badge={
          <div className="flex items-center gap-2">
            {isDemonstration && (
              <Badge tone="attention" size="sm">SAMPLE DATA</Badge>
            )}
            <Badge tone={incidentId ? "info" : "neutral"} size="sm">
              {incidentId ? `INCIDENT: ${incidentId}` : "STANDBY"}
            </Badge>
          </div>
        }
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowCreateModal(true)}
              disabled={loading || isPipelineActive}
              leadingIcon={<Plus className="h-3.5 w-3.5" />}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Create Incident
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleTriggerUpload}
              disabled={loading || isPipelineActive}
              leadingIcon={<Upload className="h-3.5 w-3.5" />}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Upload incident package
            </Button>

            <Button
              variant="outline"
              size="sm"
              onClick={handleLoadGolden}
              disabled={loading || isPipelineActive}
              leadingIcon={<Download className="h-3.5 w-3.5" />}
              loading={loading}
              loadingText="Initializing..."
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Load Golden
            </Button>

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
                Start Investigation
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
          </div>
        }
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

      {/* WORKBENCH VIEW 1: INTAKE WORKBENCH (Rendered when no incident is loaded) */}
      {!incidentId && (
        <InstrumentPanel
          title="Welcome to Cauveris Reality Debugger"
          subtitle="Forensic archive ingestion & security perimeter"
          className="border-dashed"
        >
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDraggingPackage(true);
            }}
            onDragLeave={() => setIsDraggingPackage(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDraggingPackage(false);
              const file = e.dataTransfer.files?.[0];
              if (file) processUploadFile(file);
            }}
            className={`p-8 flex flex-col items-center justify-center text-center transition-colors rounded-[var(--radius-sm,4px)] border ${
              isDraggingPackage
                ? "bg-blue-50/50 border-[var(--color-accent,#0969da)]"
                : "bg-[var(--color-canvas-subtle,#f8f9fa)] border-[var(--color-border-default,#d9e0e7)] border-dashed border-2"
            }`}
          >
            <div className="w-12 h-12 flex items-center justify-center rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-muted,#5f6b76)] mb-3">
              <FileArchive className="w-6 h-6" />
            </div>

            <h2 className="text-base font-bold text-[var(--text-primary,#f4f4f5)] mb-1">
              Drop Incident Package Archive (.zip, .tar.gz)
            </h2>
            <p className="text-xs text-[var(--text-tertiary,#71717a)] max-w-md mb-4 font-sans">
              Cauveris securely inspects magic bytes, calculates SHA-256 hashes, normalizes telemetry signals with strict provenance, and refuses unsupported repairs safely.
            </p>

            <div className="flex flex-wrap items-center justify-center gap-3">
              <Button
                variant="primary"
                size="sm"
                onClick={handleTriggerUpload}
                leadingIcon={<Upload className="w-3.5 h-3.5" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Upload incident package
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowCreateModal(true)}
                leadingIcon={<Plus className="w-3.5 h-3.5" />}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Create Incident Workspace
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleLoadGolden}
                leadingIcon={<Download className="w-3.5 h-3.5" />}
                loading={loading}
                className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              >
                Load Sample Incident
              </Button>
            </div>

            <div className="mt-6 pt-4 border-t border-[var(--divider,#27272a)] flex items-center gap-6 text-[11px] text-[var(--text-tertiary,#71717a)]">
              <span>Limit: 50MB</span>
              <span>Formats: ZIP, TAR, MCAP, JSONL</span>
              <span>Execution: Sandboxed / No untrusted code execution</span>
            </div>
          </div>
        </InstrumentPanel>
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
              value={reportData?.verification_report?.achieved_level || "RUNTIME_VERIFIED"}
              unit="level"
              provenance="VERIFIED"
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
              value={reportData?.diagnosis?.confidence ? `${Math.round(reportData.diagnosis.confidence * 100)}` : "98"}
              unit="%"
              provenance="CALIBRATED"
              source="Digital Twin Simulator"
              uncertainty="2.4"
            />
          </div>

          {/* Capability Map */}
          <CapabilityMap
            capabilities={capabilities}
            decision={reportData?.capability_report?.honest_repair_decision || "PROCEED"}
            decisionReason={reportData?.capability_report?.decision_reason || "Deterministic model calibration supported"}
          />

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

      {/* Engineer Studio Mode Simulation Panel */}
      {engineerMode && (
        <InstrumentPanel
          title="Interactive Parameter Tuning (Engineer Studio)"
          subtitle="Real-time counterfactual simulation through the digital twin"
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-[var(--text-secondary,#a1a1aa)]">
                <span>Batching Window:</span>
                <span className="text-[var(--color-fg-default,#1f2933)] font-bold">{simBatchWindow}ms</span>
              </div>
              <input
                type="range"
                min="50"
                max="300"
                step="10"
                value={simBatchWindow}
                onChange={(e) => setSimBatchWindow(Number(e.target.value))}
                className="w-full accent-zinc-400"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-[var(--text-secondary,#a1a1aa)]">
                <span>QoS Queue Depth:</span>
                <span className="text-[var(--color-fg-default,#1f2933)] font-bold">{simQosDepth}</span>
              </div>
              <input
                type="range"
                min="1"
                max="10"
                step="1"
                value={simQosDepth}
                onChange={(e) => setSimQosDepth(Number(e.target.value))}
                className="w-full accent-zinc-400"
              />
            </div>

            <div>
              <div className="flex justify-between text-xs font-mono mb-1 text-[var(--text-secondary,#a1a1aa)]">
                <span>Clock Skew:</span>
                <span className="text-[var(--color-fg-default,#1f2933)] font-bold">{simClockSkew}ms</span>
              </div>
              <input
                type="range"
                min="-50"
                max="50"
                step="5"
                value={simClockSkew}
                onChange={(e) => setSimClockSkew(Number(e.target.value))}
                className="w-full accent-zinc-400"
              />
            </div>
          </div>
        </InstrumentPanel>
      )}

      {/* Create Incident Modal */}
      <Dialog
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Incident Investigation Workspace"
      >
        <div className="space-y-4 p-4 font-mono text-xs">
          <div>
            <label className="block text-[var(--text-secondary,#a1a1aa)] mb-1 uppercase text-[10.5px]">
              Incident Title
            </label>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="e.g. Navigation Planner Memory Exhaustion"
              className="w-full p-2 bg-[var(--workspace,#121215)] border border-[var(--divider,#27272a)] rounded-[var(--radius-sm,4px)] text-[var(--text-primary,#f4f4f5)] focus:outline-none focus:border-zinc-400"
            />
          </div>

          <div>
            <label className="block text-[var(--text-secondary,#a1a1aa)] mb-1 uppercase text-[10.5px]">
              System Identifier
            </label>
            <input
              type="text"
              value={newSystemName}
              onChange={(e) => setNewSystemName(e.target.value)}
              placeholder="e.g. AMR-NAV-04"
              className="w-full p-2 bg-[var(--workspace,#121215)] border border-[var(--divider,#27272a)] rounded-[var(--radius-sm,4px)] text-[var(--text-primary,#f4f4f5)] focus:outline-none focus:border-zinc-400"
            />
          </div>

          <div>
            <label className="block text-[var(--text-secondary,#a1a1aa)] mb-1 uppercase text-[10.5px]">
              Description
            </label>
            <textarea
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="e.g. Memory spike during sensor processing caused worker OOM kill"
              rows={2}
              className="w-full p-2 bg-[var(--workspace,#121215)] border border-[var(--divider,#27272a)] rounded-[var(--radius-sm,4px)] text-[var(--text-primary,#f4f4f5)] focus:outline-none focus:border-zinc-400 resize-none"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowCreateModal(false)}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={async () => {
                try {
                  const res = await api.create(false, {
                    title: newTitle || "Untitled Incident",
                    system_name: newSystemName,
                    description: newDescription,
                  });
                  setIncidentId(res.incident_id);
                  setShowCreateModal(false);
                  await loadIncidentsList();
                  notify(`Created incident ${res.incident_id}`, "success");
                } catch (err: any) {
                  notify(err.message || "Failed to create incident", "error");
                }
              }}
              className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            >
              Create Workspace
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
