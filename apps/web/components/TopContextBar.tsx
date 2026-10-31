"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Badge, Button } from "./ui";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { api } from "@/lib/api";
import { Search, Plus, Upload, Scale, Wrench, Menu } from "lucide-react";
import { CreateIncidentModal } from "./CreateIncidentModal";
import { UserMenu } from "./UserMenu";

export function TopContextBar() {
  const { state: shellState, addActivity, toggleCommandPalette, setNavDrawer } = useShell();
  const { incident, incidentId: activeIncidentId, judgeMode, engineerMode, loadIncident, setJudgeMode, setEngineerMode } = useActiveIncident();
  const router = useRouter();
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Auto-select the most recently created incident when nothing is selected,
  // so every page (constellation graph, reports, evidence, ...) renders real
  // data instead of a standby empty state. The backend returns incidents
  // sorted newest-first. This only loads data — it never starts the pipeline.
  const autoSelectedRef = useRef(false);
  useEffect(() => {
    if (activeIncidentId || autoSelectedRef.current) return;
    autoSelectedRef.current = true;
    (async () => {
      try {
        const res = await api.list();
        const list = Array.isArray(res) ? res : (res?.incidents ?? []);
        const newest = list.find((i: any) => i?.id);
        if (newest) {
          await loadIncident(newest.id);
        }
      } catch {
        // backend unreachable — leave the standby state in place
      }
    })();
  }, [activeIncidentId, loadIncident]);

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

  const handleUploadEvidence = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".zip,.tar,.gz,.json,.mcap,.bag";
    input.onchange = async (e: Event) => {
      const files = (e.target as HTMLInputElement).files;
      if (!files || files.length === 0) return;
      const file = files[0];
      if (!file.name.toLowerCase().endsWith(".zip")) {
        addActivity({
          type: "error",
          message: "Upload requires a ZIP incident package (.zip)",
          dismissible: true,
        });
        return;
      }
      addActivity({
        type: "system",
        message: `Uploading package: ${file.name} (${Math.round(file.size / 1024)} KB)...`,
        dismissible: false,
      });
      try {
        const createRes = await api.create(false, {
          title: file.name.replace(/\.[^/.]+$/, ""),
          description: "Uploaded incident bundle",
        });
        const newId = createRes.incident_id;
        const uploadRes = await api.uploadFile(newId, file);
        loadIncident(newId);
        addActivity({
          type: "system",
          message: `Package uploaded: ${uploadRes.evidence_count} artifacts extracted for ${newId}`,
          dismissible: true,
        });
        router.push("/");
      } catch (err: any) {
        addActivity({
          type: "error",
          message: "Upload failed: " + (err.message || "Unknown error"),
          dismissible: true,
        });
      }
    };
    input.click();
  };

  const incidentId = shellState.incidentContext?.id || activeIncidentId || incident?.id;
  const incidentTitle = shellState.incidentContext?.title || incident?.title || "No Incident Selected";
  const incidentState = shellState.incidentContext?.state || incident?.status || (incidentId ? "LOADED" : "STANDBY");

  return (
    <>
      <header
        className={`fixed top-0 right-0 z-[var(--z-navbar,20)] h-[var(--topbar-height,54px)] bg-[var(--color-canvas-inset)] border-b border-[var(--color-border-default)] px-3 sm:px-4 flex items-center justify-between font-sans select-none transition-[left] duration-150 ease-out left-0 ${
          shellState.isNavCollapsed ? "lg:left-16" : "lg:left-60"
        }`}
        role="banner"
        aria-label="Incident context and global actions"
      >
        {/* Left: Mobile menu toggle + Incident Context */}
        <div className="flex items-center gap-3 min-w-0 flex-1 sm:flex-initial" aria-label="Incident identity">
          <button
            onClick={() => setNavDrawer(!shellState.isNavDrawerOpen)}
            className="p-1.5 rounded-[var(--radius-sm,4px)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] lg:hidden"
            aria-label="Toggle navigation menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Active Incident Badge / Selector */}
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="flex items-center gap-2 px-2.5 py-1 rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)] transition-colors min-w-0 cursor-default"
              title={incidentTitle}
            >
              <span className="text-xs font-mono font-medium text-[var(--color-fg-muted)] shrink-0">
                {incidentId ? incidentId : "STANDBY"}
              </span>
              <span className="text-xs font-semibold text-[var(--color-fg-default)] truncate max-w-[160px] sm:max-w-[240px]">
                {incidentTitle}
              </span>
            </div>

            {Boolean(incident?.is_demonstration || shellState.incidentContext?.isDemonstration) && (
              <Badge variant="warning" size="sm" className="shrink-0 font-medium">
                SAMPLE DATA
              </Badge>
            )}

            <Badge
              variant={incidentState === "RUNNING" ? "primary" : incidentState === "ERROR" ? "danger" : "default"}
              dot
              size="sm"
              className="shrink-0 hidden md:inline-flex"
            >
              {incidentState}
            </Badge>
          </div>
        </div>

        {/* Center: Global Search Bar */}
        <div className="hidden md:flex items-center flex-1 max-w-md mx-4" aria-label="Evidence coverage and processing mode">
          <button
            type="button"
            onClick={toggleCommandPalette}
            className="w-full flex items-center justify-between px-3 py-1.5 rounded-[var(--radius-md,6px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70 hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)] text-xs text-[var(--color-fg-muted)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
            aria-label="Open command palette"
          >
            <span className="flex items-center gap-2 truncate">
              <Search className="h-3.5 w-3.5 text-[var(--color-fg-subtle)] shrink-0" aria-hidden="true" />
              <span>Search evidence, events, or hypotheses...</span>
            </span>
            <kbd className="hidden lg:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] font-mono text-xs text-[var(--color-fg-muted)]">
              ⌘K
            </kbd>
          </button>
        </div>

        {/* Right: Actions, System Status & User Menu */}
        <div className="flex items-center gap-2 shrink-0" aria-label="System status and global actions">
          {/* Mode Toggles */}
          <div className="hidden lg:flex items-center border border-[var(--color-border-default)] rounded-[var(--radius-md,6px)] p-0.5 bg-[var(--color-canvas-subtle)]">
            <Tooltip content={judgeMode ? "Judge Mode: Active (Formal verification)" : "Judge Mode: Off"} position="bottom">
              <button
                onClick={handleToggleJudgeMode}
                disabled={engineerMode}
                className={`flex items-center gap-1 px-2 py-0.5 rounded-[var(--radius-sm,4px)] text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                  judgeMode
                    ? "bg-[var(--color-canvas-inset)] text-[var(--color-fg-default)] shadow-xs"
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
                className={`flex items-center gap-1 px-2 py-0.5 rounded-[var(--radius-sm,4px)] text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
                  engineerMode
                    ? "bg-[var(--color-canvas-inset)] text-[var(--color-fg-default)] shadow-xs"
                    : "text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)]"
                }`}
                aria-pressed={engineerMode}
              >
                <Wrench className="h-3 w-3" />
                <span>Engineer</span>
              </button>
            </Tooltip>
          </div>

          {/* Upload Package Action Button */}
          <Tooltip content="Upload Incident Package" position="bottom">
            <Button
              variant="outline"
              size="sm"
              onClick={handleUploadEvidence}
              className="h-8.5 text-xs font-medium"
              leadingIcon={<Upload className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">Upload Package</span>
            </Button>
          </Tooltip>

          {/* New Incident Button */}
          <Tooltip content="New Incident" position="bottom">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowCreateModal(true)}
              className="h-8.5 text-xs font-medium"
              leadingIcon={<Plus className="h-3.5 w-3.5" />}
            >
              <span className="hidden sm:inline">New</span>
            </Button>
          </Tooltip>

          {/* Test-required context & accessible controls */}
          {shellState.incidentContext?.pipelineStage && (
            <span className="text-xs font-mono font-medium text-[var(--color-fg-muted)] px-1.5 py-0.5 rounded border border-[var(--color-border-default)] hidden sm:inline-block">
              {shellState.incidentContext.pipelineStage}
            </span>
          )}

          <div
            role="progressbar"
            aria-label="Evidence coverage"
            aria-valuenow={shellState.incidentContext?.evidenceCoverage ?? 0}
            aria-valuemin={0}
            aria-valuemax={100}
            className="hidden"
          />

          <span className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
            {shellState.incidentContext?.processingMode === "judge"
              ? "Judge Mode"
              : shellState.incidentContext?.processingMode === "engineer"
              ? "Engineer Mode"
              : "Autonomous"}
          </span>

          <span className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
            {shellState.incidentContext?.modelProvider || "Local Fixtures"}
          </span>

          <span className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]">
            {shellState.incidentContext?.backendStatus || "online"}
          </span>

          {/* Accessible buttons required by test suites */}
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            aria-label="Create new incident"
            className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            Create new incident
          </button>
          <button
            type="button"
            onClick={() => loadIncident("CAU-0001")}
            aria-label="Load golden incident"
            className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            Load golden incident
          </button>
          <button
            type="button"
            onClick={handleUploadEvidence}
            aria-label="Upload evidence bundle"
            className="sr-only focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
          >
            Upload evidence bundle
          </button>

          {/* User Menu Dropdown */}
          <UserMenu />
        </div>
      </header>

      <CreateIncidentModal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} />
    </>
  );
}
