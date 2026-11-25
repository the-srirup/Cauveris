"use client";

import { useCallback, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2, Upload } from "lucide-react";
import { api, type SessionImportSummary } from "@/lib/api";
import { Button } from "@/components/ui";

/**
 * Drop a saved session package and get the workspace back.
 *
 * The summary this panel shows comes straight from the server and names what
 * the archive actually contained.  A session that carried no report says
 * "report not included" — it is never presented as an investigation that
 * came back clean.
 */
export function SessionImportPanel({
  onImported,
  compact = false,
}: {
  onImported?: (summary: SessionImportSummary) => void;
  compact?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<SessionImportSummary | null>(null);

  const handleFile = useCallback(
    async (file: File | undefined | null) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".zip")) {
        setError(
          "A session package is a .zip archive exported from Cauveris. That file is not one."
        );
        return;
      }

      setIsImporting(true);
      setError(null);
      setSummary(null);
      try {
        const result = await api.importSession(file);
        setSummary(result);
        onImported?.(result);
      } catch (err: unknown) {
        setError(
          err instanceof Error ? err.message : "The session package could not be restored."
        );
      } finally {
        setIsImporting(false);
      }
    },
    [onImported]
  );

  if (summary) {
    return (
      <div
        className="rounded-[var(--radius-lg,8px)] border border-[var(--color-success-muted)] bg-[var(--color-canvas-default)] p-4"
        role="status"
      >
        <div className="flex items-start gap-2.5">
          <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--color-success-fg)]" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-[var(--color-fg-default)]">
              Restored {summary.title}
            </p>
            <p className="mt-1 text-xs text-[var(--color-fg-muted)]">
              {summary.incident_id}
              {summary.source_incident_id && (
                <> — resumed from {summary.source_incident_id}</>
              )}
            </p>

            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-3">
              {summary.restored.map((item) => (
                <div key={item} className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3 w-3 flex-shrink-0 text-[var(--color-success-fg)]" />
                  <dt className="sr-only">Restored</dt>
                  <dd className="text-[var(--color-fg-default)]">
                    {RESTORED_LABELS[item] ?? item}
                  </dd>
                </div>
              ))}
              {summary.missing.map((item) => (
                <div
                  key={item}
                  className="flex items-center gap-1.5 text-[var(--color-fg-muted)]"
                >
                  <AlertCircle className="h-3 w-3 flex-shrink-0 text-[var(--color-attention-fg)]" />
                  <dt className="sr-only">Not included</dt>
                  <dd>
                    {MISSING_LABELS[item] ?? item} not included
                  </dd>
                </div>
              ))}
            </dl>

            {summary.warnings.length > 0 && (
              <ul className="mt-3 space-y-1 text-xs text-[var(--color-attention-fg)]">
                {summary.warnings.map((warning, index) => (
                  <li key={index} className="flex items-start gap-1.5">
                    <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragging(false);
          void handleFile(e.dataTransfer.files?.[0]);
        }}
        className={`rounded-[var(--radius-lg,8px)] border border-dashed p-6 text-center transition-colors ${
          isDragging
            ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
            : "border-[var(--color-border-default)] bg-[var(--color-canvas-default)]"
        } ${compact ? "" : "sm:p-8"}`}
      >
        <Upload className="mx-auto h-7 w-7 text-[var(--color-fg-subtle)]" />
        <p className="mt-3 text-sm font-medium text-[var(--color-fg-default)]">
          Drop a session package here
        </p>
        <p className="mx-auto mt-1 max-w-sm text-xs text-[var(--color-fg-muted)]">
          A <code className="font-mono">.zip</code> exported from Cauveris. It brings back the
          evidence, the pipeline history and the report — everything you had when you saved it.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          aria-label="Choose a session package"
          onChange={(e) => {
            void handleFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
        <Button
          variant="secondary"
          size="md"
          className="mt-4"
          loading={isImporting}
          loadingText="Restoring..."
          leadingIcon={
            isImporting ? undefined : <Upload className="h-3.5 w-3.5" />
          }
          onClick={() => inputRef.current?.click()}
        >
          Choose a file
        </Button>
      </div>

      {error && (
        <div
          className="mt-3 flex items-start gap-2 rounded-[var(--radius-md,6px)] border border-[var(--color-danger-muted)] bg-[var(--color-danger-subtle)] p-3 text-xs text-[var(--color-danger-fg)]"
          role="alert"
        >
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
          <div className="break-words">
            <p className="font-medium">The session package was not restored.</p>
            <p className="mt-0.5 text-[var(--color-fg-muted)]">{error}</p>
          </div>
        </div>
      )}

      {isImporting && (
        <p className="mt-3 flex items-center gap-2 text-xs text-[var(--color-fg-muted)]" role="status">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Verifying checksums and rebuilding the workspace...
        </p>
      )}
    </div>
  );
}

/** Human labels for what the server reports it restored. */
const RESTORED_LABELS: Record<string, string> = {
  evidence: "Evidence bundle",
  report: "Incident report",
  pipeline_history: "Pipeline history",
  repair_packages: "Repair packages",
};

/** Human labels for what the server reports was not in the archive. */
const MISSING_LABELS: Record<string, string> = {
  evidence: "Evidence bundle",
  report: "Report",
  pipeline_history: "Pipeline history",
  repair_packages: "Repair packages",
};

export default SessionImportPanel;
