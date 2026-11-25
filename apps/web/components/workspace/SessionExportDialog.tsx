"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  FileArchive,
  FileText,
  History,
  Loader2,
  Package,
} from "lucide-react";
import { api } from "@/lib/api";
import { exportAndDownloadSession } from "@/lib/sessionDownload";
import { Button, Dialog } from "@/components/ui";

/**
 * Export the whole investigation as a `cauveris-session/v1` archive.
 *
 * The dialog is intentionally explicit about what the archive holds, and the
 * server's account of what was *not* included is shown next to it.  A session
 * built before the report was written says so; it never implies the
 * investigation came back clean.
 */
export function SessionExportDialog({
  open,
  onClose,
  incidentId,
}: {
  open: boolean;
  onClose: () => void;
  incidentId: string | null;
}) {
  const [isExporting, setIsExporting] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exportCount, setExportCount] = useState<number | null>(null);
  const [lastExportSize, setLastExportSize] = useState<number | null>(null);
  const [result, setResult] = useState<{
    session_id: string;
    build_number: number;
    size: number;
    file_count: number;
    missing: string[];
    warnings: string[];
    filename: string;
  } | null>(null);

  const loadHistory = useCallback(async () => {
    if (!incidentId) return;
    setIsLoadingHistory(true);
    try {
      const history = await api.listSessions(incidentId);
      const sessions = history.sessions ?? [];
      setExportCount(sessions.length);
      setLastExportSize(sessions.length > 0 ? sessions[0].size : null);
    } catch {
      // The export history is a convenience; failing to read it must not
      // block the operator from exporting.
      setExportCount(null);
      setLastExportSize(null);
    } finally {
      setIsLoadingHistory(false);
    }
  }, [incidentId]);

  useEffect(() => {
    if (!open) {
      setResult(null);
      setError(null);
      return;
    }
    void loadHistory();
  }, [open, loadHistory]);

  const handleExport = useCallback(async () => {
    if (!incidentId) return;
    setIsExporting(true);
    setError(null);
    try {
      const { built, filename } = await exportAndDownloadSession(incidentId);

      setResult({
        session_id: built.session_id,
        build_number: built.build_number,
        size: built.size,
        file_count: built.manifest?.files?.length ?? 0,
        missing: built.missing ?? [],
        warnings: built.warnings ?? [],
        filename,
      });
      void loadHistory();
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "The session package could not be exported."
      );
    } finally {
      setIsExporting(false);
    }
  }, [incidentId, loadHistory]);

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Export session package"
      description="Save the investigation as one archive you can reload later."
      size="lg"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose} disabled={isExporting}>
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => void handleExport()}
            disabled={!incidentId || isExporting}
            loading={isExporting}
            loadingText="Building..."
            leadingIcon={isExporting ? undefined : <Download className="h-3.5 w-3.5" />}
          >
            Export session
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <section aria-labelledby="session-export-contents-heading">
          <h3
            id="session-export-contents-heading"
            className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)]"
          >
            What goes in
          </h3>
          <ul className="mt-2.5 space-y-2 text-xs text-[var(--color-fg-muted)]">
            <li className="flex items-start gap-2">
              <FileArchive className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-fg-subtle)]" />
              <span>
                <strong className="font-medium text-[var(--color-fg-default)]">
                  The complete evidence bundle
                </strong>{" "}
                — every file, byte for byte.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <History className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-fg-subtle)]" />
              <span>
                <strong className="font-medium text-[var(--color-fg-default)]">
                  The pipeline stage history
                </strong>{" "}
                — status, timings, warnings and errors for every stage.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <FileText className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-fg-subtle)]" />
              <span>
                <strong className="font-medium text-[var(--color-fg-default)]">
                  The incident report
                </strong>{" "}
                — when one has been written.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Package className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-[var(--color-fg-subtle)]" />
              <span>
                <strong className="font-medium text-[var(--color-fg-default)]">
                  The repair packages
                </strong>{" "}
                — any that were already built for this incident.
              </span>
            </li>
          </ul>
        </section>

        {isLoadingHistory && (
          <p className="flex items-center gap-2 text-xs text-[var(--color-fg-muted)]" role="status">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Checking for previous exports...
          </p>
        )}

        {!isLoadingHistory && exportCount !== null && exportCount > 0 && !result && (
          <p className="text-xs text-[var(--color-fg-muted)]">
            {exportCount} previous {exportCount === 1 ? "export" : "exports"}
            {lastExportSize !== null && <> · last one {formatBytes(lastExportSize)}</>}. Exporting
            again writes a new build and leaves the earlier ones in place.
          </p>
        )}

        {result && (
          <section
            className="rounded-[var(--radius-lg,8px)] border border-[var(--color-success-muted)] bg-[var(--color-canvas-default)] p-4"
            aria-labelledby="session-export-result-heading"
            role="status"
          >
            <div className="flex items-start gap-2.5">
              <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-success-fg)]" />
              <div className="min-w-0 flex-1">
                <h3
                  id="session-export-result-heading"
                  className="text-sm font-semibold text-[var(--color-fg-default)]"
                >
                  Session exported
                </h3>
                <p className="mt-1 break-all font-mono text-[11px] text-[var(--color-fg-subtle)]">
                  {result.filename}
                </p>

                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
                  <div>
                    <dt className="text-[var(--color-fg-subtle)]">Build</dt>
                    <dd className="font-mono text-[var(--color-fg-default)]">
                      #{result.build_number}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-fg-subtle)]">Size</dt>
                    <dd className="font-mono text-[var(--color-fg-default)]">
                      {formatBytes(result.size)}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-fg-subtle)]">Files</dt>
                    <dd className="font-mono text-[var(--color-fg-default)]">
                      {result.file_count}
                    </dd>
                  </div>
                </dl>

                {result.missing.length > 0 && (
                  <ul className="mt-3 space-y-1 text-xs text-[var(--color-attention-fg)]">
                    {result.missing.map((item) => (
                      <li key={item} className="flex items-start gap-1.5">
                        <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
                        <span>
                          {MISSING_LABELS[item] ?? item} not included — this incident does not have
                          one yet.
                        </span>
                      </li>
                    ))}
                  </ul>
                )}

                {result.warnings.length > 0 && (
                  <ul className="mt-2 space-y-1 text-xs text-[var(--color-attention-fg)]">
                    {result.warnings.map((warning, index) => (
                      <li key={index} className="flex items-start gap-1.5">
                        <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
                        <span>{warning}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>
        )}

        {error && (
          <div
            className="flex items-start gap-2 rounded-[var(--radius-md,6px)] border border-[var(--color-danger-muted)] bg-[var(--color-danger-subtle)] p-3 text-xs text-[var(--color-danger-fg)]"
            role="alert"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <div className="break-words">
              <p className="font-medium">The session package was not exported.</p>
              <p className="mt-0.5 text-[var(--color-fg-muted)]">{error}</p>
            </div>
          </div>
        )}
      </div>
    </Dialog>
  );
}

/** Human labels for the parts the server reports were not in the archive. */
const MISSING_LABELS: Record<string, string> = {
  evidence: "Evidence bundle",
  report: "Report",
  pipeline_history: "Pipeline history",
  repair_packages: "Repair packages",
};

/** Human-readable size. */
function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

export default SessionExportDialog;
