"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, ArrowLeftRight, Download, FileArchive, History, Package } from "lucide-react";
import { Button, Dialog } from "@/components/ui";
import { useShell } from "@/lib/useShell";
import { useActiveIncident } from "@/lib/useIncident";
import { exportAndDownloadSession } from "@/lib/sessionDownload";
import { notify } from "@/components/Notification";

/**
 * Confirmation prompt shown before returning to the Workspace Hub when an
 * investigation is open. Gives the operator the explicit choice to save/export
 * their session package first, leave without saving, or stay on the dashboard.
 */
export function SwitchWorkspaceDialog() {
  const router = useRouter();
  const { state, setWorkspacePrompt, setIncidentContext, closeInspector } = useShell();
  const { incidentId, incident, setIncidentId } = useActiveIncident();
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = Boolean(state.workspacePromptOpen);
  const activeId = incidentId || state.incidentContext?.id || incident?.id || null;
  const activeTitle = state.incidentContext?.title || incident?.title || activeId || "Current Investigation";

  useEffect(() => {
    if (!open) {
      setError(null);
      setIsSaving(false);
    }
  }, [open]);

  const navigateToWorkspace = () => {
    closeInspector?.();
    setIncidentContext(null);
    setIncidentId(null);
    setWorkspacePrompt(false);
    router.push("/workspace");
  };

  const handleSaveAndSwitch = async () => {
    if (!activeId) {
      navigateToWorkspace();
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await exportAndDownloadSession(activeId);
      notify(`Saved session package for ${activeId}`, "success");
      navigateToWorkspace();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "The session package could not be saved. You can retry or leave without saving."
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={() => {
        if (!isSaving) setWorkspacePrompt(false);
      }}
      title="Save session before switching workspace?"
      description="You are returning to the Workspace Hub to open or create another incident."
      size="md"
      footer={
        <div className="flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setWorkspacePrompt(false)}
            disabled={isSaving}
          >
            Cancel
          </Button>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center">
            <Button
              variant="outline"
              size="sm"
              onClick={navigateToWorkspace}
              disabled={isSaving}
              leadingIcon={<ArrowLeftRight className="h-3.5 w-3.5" />}
            >
              Don&apos;t save &amp; switch
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => void handleSaveAndSwitch()}
              disabled={isSaving}
              loading={isSaving}
              loadingText="Saving session..."
              leadingIcon={isSaving ? undefined : <Download className="h-3.5 w-3.5" />}
            >
              Save session &amp; switch
            </Button>
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {activeId && (
          <div className="rounded-[var(--radius-md,6px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] px-3.5 py-2.5">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)]">
              Active Investigation
            </p>
            <div className="mt-1 flex items-center gap-2 min-w-0">
              <span className="font-mono text-xs font-medium text-[var(--color-fg-muted)] shrink-0">
                {activeId}
              </span>
              <span className="text-xs text-[var(--color-border-default)]">•</span>
              <span className="truncate text-sm font-medium text-[var(--color-fg-default)]">
                {activeTitle}
              </span>
            </div>
          </div>
        )}

        <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
          Would you like to export a portable <code className="font-mono">.zip</code> session
          package before leaving? Your choice — you can resume without saving from Recent
          Investigations on the workspace, or download a complete archive now.
        </p>

        <ul className="space-y-1.5 text-xs text-[var(--color-fg-muted)]">
          <li className="flex items-center gap-2">
            <FileArchive className="h-3.5 w-3.5 shrink-0 text-[var(--color-fg-subtle)]" />
            <span>Complete evidence bundle and checksums</span>
          </li>
          <li className="flex items-center gap-2">
            <History className="h-3.5 w-3.5 shrink-0 text-[var(--color-fg-subtle)]" />
            <span>Pipeline stage progression, events, and report</span>
          </li>
          <li className="flex items-center gap-2">
            <Package className="h-3.5 w-3.5 shrink-0 text-[var(--color-fg-subtle)]" />
            <span>Any repair packages generated for this incident</span>
          </li>
        </ul>

        {error && (
          <div
            className="flex items-start gap-2 rounded-[var(--radius-md,6px)] border border-[var(--color-danger-muted)] bg-[var(--color-danger-subtle)] p-3 text-xs text-[var(--color-danger-fg)]"
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div className="break-words">
              <p className="font-medium">Session export failed</p>
              <p className="mt-0.5 text-[var(--color-fg-muted)]">{error}</p>
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}

export default SwitchWorkspaceDialog;
