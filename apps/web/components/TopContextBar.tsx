"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Badge, Button, Tooltip } from "./ui";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { exportAndDownloadSession } from "@/lib/sessionDownload";
import { notify } from "./Notification";
import { Plus, Scale, Wrench, Menu, Search, FolderOpen, Download, Terminal } from "lucide-react";
import { UserMenu } from "./UserMenu";

/**
 * The console's top bar.
 *
 * Fixed across the entire top width of the page, above both the left sidebar
 * panel and the main investigation body.
 */
export function TopContextBar() {
  const {
    state: shellState,
    addActivity,
    setNavDrawer,
    setCommandPalette,
    setWorkspacePrompt,
    openInspector,
    closeInspector,
  } = useShell();
  const { incident, incidentId: activeIncidentId, judgeMode, engineerMode, setJudgeMode, setEngineerMode } = useActiveIncident();
  const router = useRouter();
  const [isSavingSession, setIsSavingSession] = useState(false);

  const handleToggleJudgeMode = () => {
    if (engineerMode) return;
    const newValue = !judgeMode;
    setJudgeMode(newValue);
    if (newValue) {
      setEngineerMode(false);
    }
    addActivity({
      type: "system",
      message: newValue ? "Judge Mode enabled — Formal verification active" : "Judge Mode disabled",
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
      message: newValue ? "Engineer Mode enabled — Live twin active" : "Engineer Mode disabled",
      dismissible: true,
    });
  };

  const incidentId = shellState.incidentContext?.id || activeIncidentId || incident?.id;
  const incidentTitle = shellState.incidentContext?.title || incident?.title || "No Incident Selected";
  const incidentState = shellState.incidentContext?.state || incident?.status || (incidentId ? "LOADED" : "STANDBY");
  const activeStage = shellState.incidentContext?.pipelineStage;
  const backendStatus = shellState.incidentContext?.backendStatus || "online";
  const modelProvider = shellState.incidentContext?.modelProvider || "Local Fixtures";

  /*
   * The status badge names the active stage while the pipeline is running,
   * so the stage is available without a second chip on the bar.
   */
  const statusTitle = activeStage
    ? `${incidentState} — stage: ${activeStage}`
    : incidentState;

  const handleGoToWorkspace = () => {
    if (incidentId && typeof setWorkspacePrompt === "function") {
      setWorkspacePrompt(true);
    } else {
      router.push("/workspace");
    }
  };

  const handleQuickSaveSession = async () => {
    if (!incidentId || isSavingSession) return;
    setIsSavingSession(true);
    try {
      await exportAndDownloadSession(incidentId);
      notify(`Saved session package for ${incidentId}`, "success");
    } catch (err: unknown) {
      notify(
        err instanceof Error ? err.message : "Could not export session package.",
        "error"
      );
    } finally {
      setIsSavingSession(false);
    }
  };

  const handleToggleConsole = () => {
    if (shellState.inspectorOpen) {
      closeInspector?.();
    } else {
      openInspector?.("evidence", { mode: "evidence" }, shellState.inspectorDockPosition || "bottom");
    }
  };

  return (
    <header
      className="fixed top-0 left-0 right-0 z-[25] h-[var(--topbar-height,54px)] bg-[var(--surface-well,var(--color-canvas-inset))] shadow-[0_1px_0_rgba(255,255,255,0.04),0_2px_8px_rgba(0,0,0,0.22)] px-3 sm:px-4 flex items-center justify-between font-sans select-none"
      role="banner"
      aria-label="Incident context and global actions"
    >
      {/* Left: Mobile menu toggle + Brand + Incident Context */}
      <div className="flex items-center gap-2.5 sm:gap-3 min-w-0 flex-1 sm:flex-initial" aria-label="Incident identity">
        <button
          onClick={() => setNavDrawer(!shellState.isNavDrawerOpen)}
          className="p-1.5 rounded-[var(--radius-sm,4px)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] lg:hidden"
          aria-label="Toggle navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        {/* Full-bar Brand Mark */}
        <Tooltip content="Return to Workspace Hub" position="bottom">
          <button
            type="button"
            onClick={handleGoToWorkspace}
            className="hidden lg:flex items-center gap-2 pr-2 rounded-[var(--radius-sm,4px)] hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] shrink-0"
            aria-label="Cauveris Workspace Home"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent)] text-[var(--color-fg-on-emphasis)] shadow-[var(--shadow-sm)] ring-1 ring-[var(--color-accent-hover)]/30">
              <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2} viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7Z" />
              </svg>
            </span>
            <span className="text-sm font-semibold tracking-tight text-[var(--color-fg-default)]">
              Cauveris
            </span>
          </button>
        </Tooltip>

        {/* Active Incident Badge / Selector */}
        <div className="flex items-center gap-2 min-w-0">
          <div
            className="flex items-center gap-2 px-2.5 h-8.5 rounded-[var(--radius-sm,4px)] bg-[var(--color-canvas-default)] transition-colors min-w-0 cursor-default"
            title={incidentTitle}
          >
            <span className="text-xs font-mono font-medium text-[var(--color-fg-muted)] shrink-0">
              {incidentId ? incidentId : "STANDBY"}
            </span>
            <span className="text-xs font-semibold text-[var(--color-fg-default)] truncate max-w-[150px] sm:max-w-[220px]">
              {incidentTitle}
            </span>
          </div>

          {Boolean(incident?.is_demonstration || shellState.incidentContext?.isDemonstration) && (
            <Badge variant="warning" size="sm" className="shrink-0 font-medium">
              SAMPLE DATA
            </Badge>
          )}

          {/* The one status readout. */}
          <span title={statusTitle}>
            <Badge
              variant={incidentState === "RUNNING" ? "primary" : incidentState === "ERROR" ? "danger" : "default"}
              dot
              size="sm"
              className="shrink-0 hidden md:inline-flex"
            >
              {incidentState}
            </Badge>
          </span>
        </div>
      </div>

      {/* Center: Global Search Bar — opens the command palette on click */}
      <div className="hidden md:flex items-center flex-1 max-w-md mx-4">
        <button
          type="button"
          onClick={() => setCommandPalette(true)}
          className="w-full h-8.5 flex items-center justify-between px-3 rounded-[var(--radius-md,6px)] bg-[var(--color-canvas-default)] hover:bg-[var(--color-canvas-muted)] text-xs text-[var(--color-fg-muted)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]"
          aria-label="Open command palette"
        >
          <span className="flex items-center gap-2 truncate">
            <Search className="h-3.5 w-3.5 text-[var(--color-fg-subtle)] shrink-0" aria-hidden="true" />
            <span>Search evidence, events, or hypotheses...</span>
          </span>
        </button>
      </div>

      {/* Right: Actions, System Status & User Menu */}
      <div className="flex items-center gap-2 shrink-0" aria-label="System status and global actions">
        {/* Live Backend Health Indicator */}
        <Tooltip content={`Backend: ${backendStatus} • Provider: ${modelProvider}`} position="bottom">
          <button
            type="button"
            onClick={() => router.push("/settings")}
            className="hidden xl:inline-flex items-center gap-1.5 h-8.5 px-2.5 rounded-[var(--radius-sm,4px)] text-xs text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-muted)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            aria-label={`System status: ${backendStatus}`}
          >
            <span
              className={`h-2 w-2 rounded-full shrink-0 ${
                backendStatus === "online"
                  ? "bg-[var(--color-success-fg,#3fb950)]"
                  : backendStatus === "degraded"
                    ? "bg-[var(--color-attention-fg,#d29922)]"
                    : "bg-[var(--color-danger-fg,#f85149)]"
              }`}
            />
            <span className="capitalize">{backendStatus}</span>
          </button>
        </Tooltip>

        {/* Mode Toggles */}
        <div className="hidden lg:flex items-center rounded-[var(--radius-sm,4px)] p-0.5 bg-[var(--color-canvas-default)]">
          <Tooltip content={judgeMode ? "Judge Mode: Active (Formal verification)" : "Judge Mode: Off"} position="bottom">
            <button
              onClick={handleToggleJudgeMode}
              disabled={engineerMode}
              className={`flex items-center gap-1 px-2 h-7.5 rounded-[var(--radius-sm,4px)] text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                judgeMode
                  ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)] shadow-[var(--shadow-sm)]"
                  : "text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
              }`}
              aria-pressed={judgeMode}
            >
              <Scale className="h-3 w-3" />
              <span>Judge</span>
            </button>
          </Tooltip>
          <Tooltip content={engineerMode ? "Engineer Mode: Active (Live digital twin)" : "Engineer Mode: Off"} position="bottom">
            <button
              onClick={handleToggleEngineerMode}
              disabled={judgeMode}
              className={`flex items-center gap-1 px-2 h-7.5 rounded-[var(--radius-sm,4px)] text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                engineerMode
                  ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)] shadow-[var(--shadow-sm)]"
                  : "text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
              }`}
              aria-pressed={engineerMode}
            >
              <Wrench className="h-3 w-3" />
              <span>Engineer</span>
            </button>
          </Tooltip>
        </div>

        {/* Forensic Console Drawer Toggle */}
        <Tooltip content={shellState.inspectorOpen ? "Close forensic console" : "Open forensic console"} position="bottom">
          <button
            type="button"
            onClick={handleToggleConsole}
            className={`inline-flex items-center justify-center h-8.5 w-8.5 rounded-[var(--radius-sm,4px)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
              shellState.inspectorOpen
                ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)]"
                : "bg-[var(--color-canvas-muted)]/65 dark:bg-[var(--color-canvas-muted)] text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-muted)] dark:hover:bg-[var(--color-border-default)]"
            }`}
            aria-label="Toggle forensic console"
            aria-pressed={Boolean(shellState.inspectorOpen)}
          >
            <Terminal className="h-4 w-4" aria-hidden="true" />
          </button>
        </Tooltip>

        {/* Quick Save Session — export archive from anywhere while multitasking */}
        {incidentId && (
          <Tooltip content="Save / export current session (.zip)" position="bottom">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void handleQuickSaveSession()}
              loading={isSavingSession}
              loadingText="Saving..."
              className="h-8.5 text-xs font-medium"
              leadingIcon={isSavingSession ? undefined : <Download className="h-3.5 w-3.5" />}
              aria-label="Save session package"
            >
              <span className="hidden md:inline">Save</span>
            </Button>
          </Tooltip>
        )}

        {/* Workspace — switch incident or return to Workspace Hub */}
        <Tooltip content="Switch workspace (change incident)" position="bottom">
          <Button
            variant="outline"
            size="sm"
            onClick={handleGoToWorkspace}
            className="h-8.5 text-xs font-medium"
            leadingIcon={<FolderOpen className="h-3.5 w-3.5" />}
            aria-label="Back to workspace"
          >
            <span className="hidden md:inline">Workspace</span>
          </Button>
        </Tooltip>

        {/* New — a shortcut into the wizard. */}
        <Tooltip content="New incident" position="bottom">
          <Button
            variant="primary"
            size="sm"
            onClick={() => router.push("/workspace/new")}
            className="h-8.5 text-xs font-medium"
            leadingIcon={<Plus className="h-3.5 w-3.5" />}
            aria-label="Create new incident"
          >
            <span className="hidden sm:inline">New</span>
          </Button>
        </Tooltip>

        <div
          role="progressbar"
          aria-label="Evidence coverage"
          aria-valuenow={shellState.incidentContext?.evidenceCoverage ?? 0}
          aria-valuemin={0}
          aria-valuemax={100}
          className="hidden"
        />

        <span className="sr-only">
          {shellState.incidentContext?.processingMode === "judge"
            ? "Judge Mode"
            : shellState.incidentContext?.processingMode === "engineer"
            ? "Engineer Mode"
            : "Autonomous"}
        </span>

        <span className="sr-only">
          {modelProvider}
        </span>

        {/* User Menu Dropdown (icon button matching navbar button height) */}
        <UserMenu />
      </div>
    </header>
  );
}
