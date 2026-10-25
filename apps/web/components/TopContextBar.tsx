"use client";

import { type ReactNode, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Button, Progress } from "./ui";
import { Tooltip } from "./Tooltip";
import { Divider } from "./Divider";
import { Toolbar, ToolbarGroup, ToolbarSeparator, ToolbarItem, ToolbarSpacer } from "./ui/Toolbar";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { api } from "@/lib/api";
import { useShellLayout } from "@/hooks/useMediaQuery";
import { Bot, Scale, Wrench, Search, Plus, Download, Upload } from "lucide-react";
import { CreateIncidentModal } from "./CreateIncidentModal";
import { UserMenu } from "./UserMenu";
import { useAuthStore } from "@/lib/auth";

function MicroProgress({ value, size = 16 }: { value: number; size?: number }) {
  const radius = (size - 2) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - value / 100);
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
          r={6.5}
          fill="none"
          stroke="var(--color-border-default)"
          strokeWidth="1.5"
        />
        <circle
          cx="8"
          cy="8"
          r={6.5}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="text-[var(--color-accent-fg)] transition-all duration-500"
          style={{ transformOrigin: "center" }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[9px] font-mono font-semibold text-[var(--color-fg-default)]">
        {Math.round(value)}%
      </span>
    </div>
  );
}

function StatusIndicator({ status, label }: { status: "online" | "degraded" | "offline"; label: string }) {
  const tones = {
    online: "bg-[var(--color-success-emphasis)]",
    degraded: "bg-[var(--color-attention-emphasis)]",
    offline: "bg-[var(--color-danger-emphasis)]",
  };

  return (
    <Tooltip content={label} position="bottom">
      <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-[var(--radius-full)] text-xs font-medium bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] shrink-0">
        <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${tones[status]}`} />
        <span className="capitalize leading-none">{status}</span>
      </span>
    </Tooltip>
  );
}

function ProcessingModeBadge({ mode }: { mode: "autonomous" | "judge" | "engineer" }) {
  const config = {
    autonomous: { label: "Autonomous", variant: "default" as const, Icon: Bot },
    judge: { label: "Judge Mode", variant: "warning" as const, Icon: Scale },
    engineer: { label: "Engineer Mode", variant: "primary" as const, Icon: Wrench },
  };
  const c = config[mode];
  return (
    <Tooltip content={`Processing: ${c.label}`} position="bottom">
      <Badge variant={c.variant} dot className="shrink-0 h-7 px-2.5 inline-flex items-center text-xs">
        <c.Icon className="h-3.5 w-3.5 mr-1.5 shrink-0" aria-hidden="true" />
        <span className="leading-none">{c.label}</span>
      </Badge>
    </Tooltip>
  );
}

export function TopContextBar() {
  const { state: shellState, setIncidentContext, addActivity, toggleCommandPalette } = useShell();
  const { incident, judgeMode, engineerMode, loadIncident, setJudgeMode, setEngineerMode } = useActiveIncident();
  const router = useRouter();
  const { isSidebarDrawer } = useShellLayout();
  const [isLoadingIncident, setIsLoadingIncident] = useState(false);

  const [showCreateModal, setShowCreateModal] = useState(false);

  const handleCreateIncident = () => {
    setShowCreateModal(true);
  };

  const handleToggleJudgeMode = () => {
    if (engineerMode) return;
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
    if (judgeMode) return;
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

  // Incident context from shell
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
        className={`
          fixed top-0 right-0 z-[var(--z-navbar)]
          h-[var(--shell-topbar-height)]
          bg-[var(--color-canvas-inset)] border-b border-[var(--color-border-default)]
          transition-all duration-200 ease-out
          left-0 lg:left-[var(--shell-sidebar-current-width,var(--sidebar-expanded-width))]
        `}
        role="banner"
        aria-label="Incident context and global actions"
      >
        <Toolbar
          className="h-full px-4 py-0 flex-nowrap justify-between"
          bordered={false}
          aria-label="Global toolbar"
        >
          {/* LEFT ZONE: Incident Identity & Context */}
          <ToolbarGroup aria-label="Incident identity" className="flex-1 min-w-0 h-full flex items-center gap-2">
            <Tooltip content="Incident ID" position="bottom">
              <span className="font-mono text-xs font-semibold px-2.5 h-7 inline-flex items-center rounded-[var(--radius-sm)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-fg-default)] shrink-0 tracking-wider">
                {incidentId || "—"}
              </span>
            </Tooltip>
            <Divider orientation="vertical" className="h-4 opacity-40 shrink-0 mx-1" />
            <div className="min-w-0 flex-1 flex items-center">
              <h2 className="text-sm font-semibold text-[var(--color-fg-default)] truncate max-w-[140px] sm:max-w-[200px] md:max-w-[300px] xl:max-w-[440px] leading-normal m-0">
                {incidentTitle}
              </h2>
            </div>
            <Badge
              variant={incidentState === "RUNNING" ? "success" : incidentState === "ERROR" ? "danger" : "muted"}
              dot
              className="shrink-0 h-7 px-2.5 inline-flex items-center text-xs ml-1"
            >
              {incidentState}
            </Badge>
            {incidentState !== pipelineStage && (
              <Tooltip content={`Pipeline stage: ${pipelineStage}`} position="bottom">
                <Badge
                  variant={pipelineStage === "COMPLETE" ? "success" : "primary"}
                  className="shrink-0 h-7 px-2.5 inline-flex items-center text-xs ml-1"
                >
                  {pipelineStage}
                </Badge>
              </Tooltip>
            )}
          </ToolbarGroup>

          {/* CENTER ZONE: Evidence Coverage & Processing Mode */}
          <ToolbarGroup aria-label="Evidence coverage and processing mode" className="flex-1 min-w-0 justify-center md:justify-start hidden md:flex h-full items-center gap-2">
            <div className="shrink-0 flex items-center" aria-label="Processing mode">
              <ProcessingModeBadge mode={processingMode} />
            </div>
            {incidentId && (
              <Tooltip content={`Evidence coverage: ${evidenceCoverage}%`} position="bottom">
                <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-[var(--radius-full)] text-xs font-medium bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-fg-muted)] shrink-0">
                  <span className="text-[11px] font-medium text-[var(--color-fg-subtle)] leading-none">Evidence</span>
                  <MicroProgress value={evidenceCoverage} size={18} />
                </span>
              </Tooltip>
            )}
          </ToolbarGroup>

          {/* RIGHT ZONE: System Status + Mode Toggles + Global Actions + User Menu */}
          <ToolbarGroup aria-label="System status and global actions" className="flex-1 min-w-0 justify-end h-full items-center">
            <div className="flex items-center gap-2 shrink-0 h-full">
              {/* System Status (hidden on mobile) */}
              <div className="hidden sm:flex items-center gap-2 shrink-0 h-full">
                <Tooltip content={`Model: ${modelProvider}`} position="bottom">
                  <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-[var(--radius-full)] text-xs font-medium bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] text-[var(--color-fg-muted)] max-w-[140px] truncate">
                    <span className="truncate leading-none">{displayModelProvider}</span>
                  </span>
                </Tooltip>
                <StatusIndicator status={backendStatus} label={`Backend: ${backendStatus}`} />
              </div>

              {/* Judge / Engineer Mode Toggles */}
              <div className="flex items-center gap-1 shrink-0 h-full">
                <Tooltip content={judgeMode ? "Judge Mode: ON (Formal verification gates)" : "Judge Mode: OFF"} position="bottom">
                  <Button
                    variant={judgeMode ? "primary" : "ghost"}
                    size="sm"
                    onClick={handleToggleJudgeMode}
                    disabled={engineerMode}
                    aria-label="Toggle Judge Mode"
                    aria-pressed={judgeMode}
                    className="h-7 px-2.5 text-xs font-medium inline-flex items-center justify-center"
                    leadingIcon={<Scale className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  >
                    Judge
                  </Button>
                </Tooltip>

                <Tooltip content={engineerMode ? "Engineer Mode: ON (Live digital twin studio)" : "Engineer Mode: OFF"} position="bottom">
                  <Button
                    variant={engineerMode ? "primary" : "ghost"}
                    size="sm"
                    onClick={handleToggleEngineerMode}
                    disabled={judgeMode}
                    aria-label="Toggle Engineer Mode"
                    aria-pressed={engineerMode}
                    className="h-7 px-2.5 text-xs font-medium inline-flex items-center justify-center"
                    leadingIcon={<Wrench className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  >
                    Engineer
                  </Button>
                </Tooltip>
              </div>

              {/* Global Actions */}
              <div className="flex items-center gap-1 shrink-0 h-full">
                <Tooltip content="Create Incident" position="bottom">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCreateIncident}
                    disabled={isLoadingIncident}
                    aria-label="Create new incident"
                    className="h-7 w-7 p-0 inline-flex items-center justify-center"
                    leadingIcon={<Plus className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  />
                </Tooltip>
                <Tooltip content="Load Golden Incident" position="bottom">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleLoadGolden}
                    disabled={isLoadingIncident}
                    aria-label="Load golden incident"
                    className="h-7 w-7 p-0 inline-flex items-center justify-center"
                    leadingIcon={<Download className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  />
                </Tooltip>
                <Tooltip content="Upload Evidence" position="bottom">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleUploadEvidence}
                    aria-label="Upload evidence bundle"
                    className="h-7 w-7 p-0 inline-flex items-center justify-center"
                    leadingIcon={<Upload className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  />
                </Tooltip>
                <Tooltip content="Command Palette (⌘K)" position="bottom">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={toggleCommandPalette}
                    aria-label="Open command palette"
                    className="h-7 w-7 p-0 inline-flex items-center justify-center"
                    leadingIcon={<Search className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />}
                  />
                </Tooltip>
                <UserMenu />
              </div>
            </div>
          </ToolbarGroup>
        </Toolbar>
      </header>

      <CreateIncidentModal isOpen={showCreateModal} onClose={handleCreateModalClose} />
    </>
  );
}