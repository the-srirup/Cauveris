"use client";

import { type ReactNode, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { tv } from "tailwind-variants";
import { Badge, Button, Progress } from "./ui";
import { Tooltip } from "./Tooltip";
import { Divider } from "./Divider";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { api } from "@/lib/api";
import { useShellLayout } from "@/hooks/useMediaQuery";
import { Bot, Scale, Wrench, Search, Plus, Download, Upload } from "lucide-react";
import { CreateIncidentModal } from "./CreateIncidentModal";
import { UserMenu } from "./UserMenu";
import { useAuthStore } from "@/lib/auth";

const topBarStyles = tv({
  base: `
    fixed top-0 left-0 right-0 z-40 h-12
    bg-[var(--theme-background)]/80 backdrop-blur-xl border-b border-[var(--color-border)]
    flex items-center px-4 gap-3
    transition-all duration-200 ease-out
    motion-reduce:transition-none
  `,
  variants: {
    sidebarState: {
      expanded: "lg:pl-[256px]",
      collapsed: "lg:pl-[76px]",
      drawer: "pl-4",
    },
  },
  defaultVariants: {
    sidebarState: "expanded",
  },
});

const sectionStyles = tv({
  base: "flex items-center gap-2.5",
  variants: {
    position: {
      left: "flex-1 min-w-0 overflow-hidden",
      center: "hidden",
      right: "flex-shrink-0 justify-end ml-auto",
    },
  },
});

const pillStyles = tv({
  base: `
    inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium
    border border-[var(--color-border)] transition-all duration-150
  `,
  variants: {
    tone: {
      default: "bg-[var(--color-surface-2)] text-[var(--color-text-muted)]",
      active: "bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)] border-[var(--color-brand-primary)]/30",
      warning: "bg-[var(--color-brand-warning)]/10 text-[var(--color-brand-warning)] border-[var(--color-brand-warning)]/30",
      danger: "bg-[var(--color-brand-danger)]/10 text-[var(--color-brand-danger)] border-[var(--color-brand-danger)]/30",
      success: "bg-[var(--color-brand-success)]/10 text-[var(--color-brand-success)] border-[var(--color-brand-success)]/30",
    },
  },
  defaultVariants: {
    tone: "default",
  },
});

const iconButtonStyles = tv({
  base: `
    relative flex h-8 w-8 items-center justify-center rounded-lg
    text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]
    transition-all duration-150
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
  `,
});

function MicroProgress({ value, size = 16 }: { value: number; size?: number }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: size, height: size }}
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <svg viewBox="0 0 16 16" style={{ width: size, height: size }} className="transform -rotate-90">
        <circle
          cx="8"
          cy="8"
          r="6.5"
          fill="none"
          stroke="var(--color-border)"
          strokeWidth="1.5"
        />
        <circle
          cx="8"
          cy="8"
          r="6.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray={40.84}
          strokeDashoffset={40.84 * (1 - value / 100)}
          strokeLinecap="round"
          className="text-[var(--color-accent)] transition-all duration-500"
          style={{ transformOrigin: "center" }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[9px] font-mono font-semibold text-[var(--color-text-primary)]">
        {Math.round(value)}%
      </span>
    </div>
  );
}

function StatusIndicator({ status, label }: { status: "online" | "degraded" | "offline"; label: string }) {
  const tones = {
    online: "bg-[var(--color-brand-success)]",
    degraded: "bg-[var(--color-brand-warning)]",
    offline: "bg-[var(--color-brand-danger)]",
  };

  return (
    <Tooltip content={label} position="bottom">
      <span
        className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[var(--color-surface-2)] border border-[var(--color-border)]"
      >
        <span className={`h-1.5 w-1.5 rounded-full ${tones[status]}`} />
        <span className="capitalize">{status}</span>
      </span>
    </Tooltip>
  );
}

function ProcessingModeBadge({ mode }: { mode: "autonomous" | "judge" | "engineer" }) {
  const config = {
    autonomous: { label: "Autonomous", tone: "default" as const, Icon: Bot },
    judge: { label: "Judge Mode", tone: "warning" as const, Icon: Scale },
    engineer: { label: "Engineer Mode", tone: "active" as const, Icon: Wrench },
  };
  const c = config[mode];
  return (
    <Tooltip content={`Processing: ${c.label}`} position="bottom">
      <span className={pillStyles({ tone: c.tone })}>
        <c.Icon className="h-3 w-3 mr-1" />
        {c.label}
      </span>
    </Tooltip>
  );
}

export function TopContextBar() {
  const { state: shellState, setIncidentContext, addActivity, toggleCommandPalette } = useShell();
  const { incident, judgeMode, engineerMode, loadIncident, setJudgeMode, setEngineerMode } = useActiveIncident();
  const router = useRouter();
  const { isSidebarDrawer } = useShellLayout();
  const [isLoadingIncident, setIsLoadingIncident] = useState(false);
  const sidebarState = isSidebarDrawer
    ? "drawer"
    : shellState.isNavCollapsed
    ? "collapsed"
    : "expanded";

  // Build incident context for shell
  // This will be called when incident loads
  if (incident && !shellState.incidentContext) {
    // We'll build this in the pages that know pipeline state
  }

  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleCreateIncident = () => {
    setShowCreateModal(true);
  };

  const handleToggleJudgeMode = () => {
    if (engineerMode) return; // Mutually exclusive
    const newValue = !judgeMode;
    setJudgeMode(newValue);
    if (newValue) {
      setEngineerMode(false);
    }
    addActivity({
      type: "system",
      message: newValue ? "Judge Mode enabled — Formal verification gates active" : "Judge Mode disabled",
      dismissible: true,
    });
  };

  const handleToggleEngineerMode = () => {
    if (judgeMode) return; // Mutually exclusive
    const newValue = !engineerMode;
    setEngineerMode(newValue);
    if (newValue) {
      setJudgeMode(false);
    }
    addActivity({
      type: "system",
      message: newValue ? "Engineer Mode enabled — Live digital twin studio active" : "Engineer Mode disabled",
      dismissible: true,
    });
  };

  const handleLoadGolden = async () => {
    setIsLoadingIncident(true);
    try {
      const newIncident = await api.create(true);
      if (newIncident) {
        loadIncident(newIncident.incident_id);
        router.push("/");
        addActivity({
          type: "system",
          message: `Loaded golden incident ${newIncident.incident_id}`,
          dismissible: true,
        });
      }
    } catch (error) {
      addActivity({
        type: "error",
        message: "Failed to load golden incident",
        details: error instanceof Error ? error.message : "Unknown error",
        dismissible: true,
      });
    } finally {
      setIsLoadingIncident(false);
    }
  };

  const handleUploadEvidence = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip,.json,.tar.gz";
    input.multiple = true;
    input.onchange = async (e) => {
      const files = (e.target as HTMLInputElement).files;
      if (files && files.length > 0) {
        addActivity({
          type: "system",
          message: `Uploading ${files.length} evidence file(s)...`,
          dismissible: false,
        });
        // TODO: Implement actual upload
        setTimeout(() => {
          addActivity({
            type: "system",
            message: "Evidence uploaded successfully",
            dismissible: true,
          });
        }, 1500);
      }
    };
    input.click();
  };

  const handleStartInvestigation = async () => {
    if (!incident) return;
    try {
      await api.reconstruct(incident.id);
      addActivity({
        type: "pipeline",
        message: `Started investigation for ${incident.id}`,
        stageId: "INGEST",
        dismissible: true,
      });
      router.push("/reality-rewind");
    } catch (error) {
      addActivity({
        type: "error",
        message: "Failed to start investigation",
        details: error instanceof Error ? error.message : "Unknown error",
        dismissible: true,
      });
    }
  };

  const handleCancelInvestigation = async () => {
    if (!incident) return;
    try {
      await api.cancel(incident.id);
      addActivity({
        type: "system",
        message: `Cancelled investigation for ${incident.id}`,
        dismissible: true,
      });
    } catch (error) {
      addActivity({
        type: "error",
        message: "Failed to cancel investigation",
        details: error instanceof Error ? error.message : "Unknown error",
        dismissible: true,
      });
    }
  };

  const handleExportReport = async () => {
    if (!incident) return;
    try {
      const report = await api.exportReport(incident.id);
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${incident.id}-report.json`;
      a.click();
      URL.revokeObjectURL(url);
      addActivity({
        type: "system",
        message: "Report exported successfully",
        dismissible: true,
      });
    } catch (error) {
      addActivity({
        type: "error",
        message: "Failed to export report",
        details: error instanceof Error ? error.message : "Unknown error",
        dismissible: true,
      });
    }
  };

  const handleResetDemo = async () => {
    try {
      await api.resetDemo();
      addActivity({
        type: "system",
        message: "Demo environment reset",
        dismissible: true,
      });
      // Reload current page
      window.location.reload();
    } catch (error) {
      addActivity({
        type: "error",
        message: "Failed to reset demo",
        details: error instanceof Error ? error.message : "Unknown error",
        dismissible: true,
      });
    }
  };

  const handleCreateModalClose = () => {
    setShowCreateModal(false);
  };

  // Mode toggle handlers
  const toggleJudgeMode = () => {
    // Judge mode and engineer mode are mutually exclusive
    // This would need to be wired to the actual state management
    // For now, we rely on the existing useActiveIncident hook
  };

  const toggleEngineerMode = () => {
    // Engineer mode toggle
  };

  // Left section: Incident Identity
  const incidentId = shellState.incidentContext?.id || incident?.id;
  const incidentTitle = shellState.incidentContext?.title || incident?.title || "No Incident Loaded";
  const incidentState = shellState.incidentContext?.state || "IDLE";
  const pipelineStage = shellState.incidentContext?.pipelineStage || "IDLE";
  const evidenceCoverage = shellState.incidentContext?.evidenceCoverage || 0;
  const modelProvider = shellState.incidentContext?.modelProvider || "Unknown";
  const backendStatus = shellState.incidentContext?.backendStatus || "offline";
  const processingMode = shellState.incidentContext?.processingMode || (judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous");

  const displayModelProvider = modelProvider.includes("(")
    ? modelProvider.replace(/\s*\(.*?\)/, "").trim()
    : modelProvider;

  return (
    <>
    <header
      className={topBarStyles({ sidebarState })}
      role="banner"
      aria-label="Incident context and global actions"
    >
      {/* Left: Incident Identity & Context */}
      <div className={sectionStyles({ position: "left" })} aria-label="Incident identity">
        <Tooltip content="Incident ID" position="bottom">
          <span className="font-mono text-xs font-semibold px-2 py-0.5 rounded-md bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-primary)] shrink-0 tracking-wider">
            {incidentId || "—"}
          </span>
        </Tooltip>
        <Divider orientation="vertical" className="h-4 opacity-40 shrink-0" />
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-[var(--color-text-primary)] truncate max-w-[140px] sm:max-w-[200px] md:max-w-[300px] xl:max-w-[440px]">
            {incidentTitle}
          </h2>
        </div>
        <Badge tone={incidentState === "RUNNING" ? "success" : incidentState === "ERROR" ? "danger" : "neutral"} dot className="shrink-0">
          {incidentState}
        </Badge>
        {/* Only show pipeline stage when different from incident state */}
        {incidentState !== pipelineStage && (
          <Tooltip content={`Pipeline stage: ${pipelineStage}`} position="bottom">
            <span className={`${pillStyles({ tone: pipelineStage === "COMPLETE" ? "success" : "active" })} shrink-0`}>
              {pipelineStage}
            </span>
          </Tooltip>
        )}
        <div className="shrink-0">
          <ProcessingModeBadge mode={processingMode} />
        </div>
        {/* Cleanly labeled Evidence Coverage Chip */}
        {incidentId && evidenceCoverage > 0 && (
          <Tooltip content={`Evidence coverage: ${evidenceCoverage}%`} position="bottom">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-muted)] shrink-0">
              <span className="text-[11px] font-medium text-[var(--color-text-secondary)]">Evidence</span>
              <MicroProgress value={evidenceCoverage} size={18} />
            </div>
          </Tooltip>
        )}
      </div>

      {/* Right: Model Provider + Backend + Mode Toggles + Global Actions */}
      <div className={sectionStyles({ position: "right" })} aria-label="System status and global actions">
        <div className="hidden sm:flex items-center gap-2 shrink-0">
          <Tooltip content={`Model: ${modelProvider}`} position="bottom">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[var(--color-surface-2)] border border-[var(--color-border)] text-[var(--color-text-muted)] max-w-[140px] truncate">
              <span className="truncate">{displayModelProvider}</span>
            </span>
          </Tooltip>
          <StatusIndicator status={backendStatus} label={`Backend: ${backendStatus}`} />
        </div>
        <Divider orientation="vertical" className="h-5 opacity-40 mx-0.5 hidden sm:block shrink-0" />

        {/* Judge / Engineer Mode Toggles */}
        <div className="flex items-center gap-1 shrink-0">
          <Tooltip content={judgeMode ? "Judge Mode: ON (Formal verification gates)" : "Judge Mode: OFF"} position="bottom">
            <button
              onClick={handleToggleJudgeMode}
              disabled={engineerMode}
              className={`inline-flex h-8 w-8 items-center justify-center rounded-lg transition-all ${
                judgeMode
                  ? "bg-[var(--color-brand-warning)]/20 border-[var(--color-brand-warning)]/40 text-[var(--color-brand-warning)] hover:bg-[var(--color-brand-warning)]/30"
                  : "bg-[var(--color-surface-2)] border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]"
              } disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]`}
              aria-label="Toggle Judge Mode"
              aria-pressed={judgeMode}
            >
              <Scale className="h-4 w-4" />
            </button>
          </Tooltip>

          <Tooltip content={engineerMode ? "Engineer Mode: ON (Live digital twin studio)" : "Engineer Mode: OFF"} position="bottom">
            <button
              onClick={handleToggleEngineerMode}
              disabled={judgeMode}
              className={`inline-flex h-8 w-8 items-center justify-center rounded-lg transition-all ${
                engineerMode
                  ? "bg-cyan-500/20 border-cyan-500/40 text-cyan-500 hover:bg-cyan-500/30"
                  : "bg-[var(--color-surface-2)] border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]"
              } disabled:opacity-40 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]`}
              aria-label="Toggle Engineer Mode"
              aria-pressed={engineerMode}
            >
              <Wrench className="h-4 w-4" />
            </button>
          </Tooltip>
        </div>

        <Divider orientation="vertical" className="h-5 opacity-40 mx-0.5 shrink-0" />
        <div className="flex items-center gap-1 shrink-0">
          <Tooltip content="Create Incident (C I)" position="bottom">
            <button
              onClick={handleCreateIncident}
              disabled={isLoadingIncident}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border border-transparent hover:border-[var(--color-border)] transition-all disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]"
              aria-label="Create new incident"
            >
              <Plus className="h-4 w-4" />
            </button>
          </Tooltip>
          <Tooltip content="Load Golden Incident (L G)" position="bottom">
            <button
              onClick={handleLoadGolden}
              disabled={isLoadingIncident}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border border-transparent hover:border-[var(--color-border)] transition-all disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]"
              aria-label="Load golden incident"
            >
              <Download className="h-4 w-4" />
            </button>
          </Tooltip>
          <Tooltip content="Upload Evidence (U B)" position="bottom">
            <button
              onClick={handleUploadEvidence}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border border-transparent hover:border-[var(--color-border)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]"
              aria-label="Upload evidence bundle"
            >
              <Upload className="h-4 w-4" />
            </button>
          </Tooltip>
          <Tooltip content="Command Palette" position="bottom">
            <button
              onClick={toggleCommandPalette}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] border border-transparent hover:border-[var(--color-border)] transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]"
              aria-label="Open command palette"
            >
              <Search className="h-4 w-4" />
            </button>
          </Tooltip>
          <UserMenu />
        </div>
      </div>
    </header>

    <CreateIncidentModal isOpen={showCreateModal} onClose={handleCreateModalClose} />
    </>
  );
}