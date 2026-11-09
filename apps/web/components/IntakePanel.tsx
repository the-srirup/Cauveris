"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Globe,
  Loader2,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  Copy,
  Check,
  ShieldAlert,
  HelpCircle,
} from "lucide-react";
import { Button } from "@/components/ui";
import { api, IngestCapabilities } from "@/lib/api";
import { SupportedFormatsModal } from "./SupportedFormatsModal";

export interface IntakeResult {
  incident_id: string;
  source_kind?: string;
  package_sha256?: string;
  evidence_count?: number;
  warnings?: string[];
  filename?: string;
}

export interface IntakePanelProps {
  onIngestSuccess?: (result: IntakeResult) => void;
  disabled?: boolean;
  className?: string;
  compact?: boolean;
  defaultSource?: string;
  placeholder?: string;
  pollIntervalMs?: number;
}

export function IntakePanel({
  onIngestSuccess,
  disabled = false,
  className = "",
  compact = false,
  defaultSource = "",
  placeholder = "GitHub, PyPI, npm, crates, Go, git+https, or archive URL...",
  pollIntervalMs = 1500,
}: IntakePanelProps) {
  const [source, setSource] = useState(defaultSource);
  const [isIngesting, setIsIngesting] = useState(false);
  const [progressMessage, setProgressMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copiedSha, setCopiedSha] = useState(false);
  const [provenance, setProvenance] = useState<IntakeResult | null>(null);

  // Capabilities disclosure (now opened in popup modal to prevent layout disruption)
  const [capabilities, setCapabilities] = useState<IngestCapabilities | null>(null);
  const [showFormats, setShowFormats] = useState(false);
  const [loadingCaps, setLoadingCaps] = useState(false);

  const fetchCapabilities = useCallback(async () => {
    if (capabilities) return;
    setLoadingCaps(true);
    try {
      const caps = await api.getIngestCapabilities();
      setCapabilities(caps);
    } catch (err: unknown) {
      console.warn("Could not load intake capabilities", err);
    } finally {
      setLoadingCaps(false);
    }
  }, [capabilities]);

  const handleToggleFormats = () => {
    if (!showFormats && !capabilities) {
      fetchCapabilities();
    }
    setShowFormats(!showFormats);
  };

  const handleSelectExample = (example: string) => {
    setSource(example);
    setError(null);
  };

  const handleIngest = async () => {
    const trimmed = source.trim();
    if (!trimmed || isIngesting || disabled) return;

    setIsIngesting(true);
    setError(null);
    setProgressMessage("Submitting source...");
    setProvenance(null);

    try {
      const job = await api.ingestFromSource(trimmed);
      setProgressMessage(`Queued (${job.source_kind || "source"}). Fetching & extracting...`);

      const deadline = Date.now() + 10 * 60 * 1000; // 10 minute timeout
      let status = job.status;
      let result: any = null;
      let jobError: string | null = null;

      while (Date.now() < deadline) {
        const polled = await api.getIngestJob(job.job_id);
        status = polled.status;
        result = polled.result ?? null;
        jobError = polled.error ?? null;

        if (status === "running") {
          setProgressMessage("Extracting and indexing evidence artifacts...");
        }

        if (["completed", "failed", "dead_letter", "cancelled"].includes(status)) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
      }

      if (status !== "completed" || !result?.incident_id) {
        throw new Error(jobError || result?.error || `Ingest job ended with status "${status}"`);
      }

      const intakeRes: IntakeResult = {
        incident_id: result.incident_id,
        source_kind: result.source?.payload_kind || result.source?.kind || job.source_kind,
        package_sha256: result.package_sha256 || result.source?.sha256,
        evidence_count: result.evidence_count ?? 0,
        warnings: result.warnings ?? [],
        filename: result.source?.filename,
      };

      setProvenance(intakeRes);
      setProgressMessage(null);
      onIngestSuccess?.(intakeRes);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Source ingestion failed";
      setError(message);
      setProgressMessage(null);
    } finally {
      setIsIngesting(false);
    }
  };

  const handleCopySha = (sha: string) => {
    navigator.clipboard.writeText(sha);
    setCopiedSha(true);
    setTimeout(() => setCopiedSha(false), 2000);
  };

  return (
    <>
      <div
        className={`rounded-[var(--radius-md,6px)] border border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas-subtle,#18181b)] p-1.5 sm:p-2 text-xs transition-all ${className}`}
        data-testid="intake-panel"
      >
        {/* Main input row */}
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1 min-w-[200px] max-w-[320px]">
            <input
              type="text"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleIngest();
              }}
              placeholder={placeholder}
              disabled={disabled || isIngesting}
              aria-label="Universal source specification or URL"
              className="w-full h-8 rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default,#27272a)] bg-[var(--color-canvas,#09090b)] px-2.5 text-xs font-mono text-zinc-100 placeholder:text-zinc-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:opacity-50"
            />
          </div>
          <div className="flex items-center gap-1.5 flex-shrink-0">
            <Button
              variant="primary"
              size="sm"
              onClick={handleIngest}
              disabled={disabled || isIngesting || !source.trim()}
              leadingIcon={isIngesting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />}
              loading={isIngesting}
              loadingText="Ingesting..."
              className="h-8 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              Ingest
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleFormats}
              aria-expanded={showFormats}
              aria-label="Show supported formats"
              className="h-8 text-zinc-400 hover:text-zinc-200"
            >
              <HelpCircle className="h-3.5 w-3.5" />
              <span className="hidden sm:inline ml-1">Formats</span>
            </Button>
          </div>
        </div>

        {/* Progress or active status */}
        {progressMessage && (
          <div className="mt-2 flex items-center gap-2 text-indigo-400 font-mono text-[11px]" role="status">
            <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
            <span className="truncate">{progressMessage}</span>
          </div>
        )}

        {/* Error display */}
        {error && (
          <div className="mt-2 flex items-start gap-2 rounded bg-rose-950/40 border border-rose-800/60 p-1.5 text-rose-300 text-[11px]" role="alert">
            <AlertCircle className="h-3.5 w-3.5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1 break-all">{error}</div>
          </div>
        )}

        {/* Provenance card on success */}
        {provenance && (
          <div className="mt-2 rounded border border-emerald-900/60 bg-emerald-950/20 p-2 text-zinc-300 text-[11px] space-y-1">
            <div className="flex items-center justify-between text-emerald-400 font-medium">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                Ingested {provenance.incident_id}
              </span>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-emerald-900/40 border border-emerald-700/50">
                {provenance.source_kind || "package"}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-zinc-400 pt-1">
              <span>Artifacts: <strong className="text-zinc-200">{provenance.evidence_count}</strong></span>
              {provenance.package_sha256 && (
                <span className="flex items-center gap-1">
                  SHA-256:{" "}
                  <code className="text-zinc-300">{provenance.package_sha256.slice(0, 12)}...</code>
                  <button
                    type="button"
                    onClick={() => handleCopySha(provenance.package_sha256!)}
                    className="hover:text-zinc-100 p-0.5 rounded"
                    title="Copy full SHA-256"
                    aria-label="Copy SHA-256"
                  >
                    {copiedSha ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                  </button>
                </span>
              )}
            </div>
            {provenance.warnings && provenance.warnings.length > 0 && (
              <div className="mt-1 text-[10px] text-amber-400/90 space-y-0.5">
                {provenance.warnings.map((w, idx) => (
                  <div key={idx} className="flex items-center gap-1">
                    <ShieldAlert className="h-3 w-3 flex-shrink-0" />
                    <span>{w}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Formats Reference Pop-up Window - Prevents layout breaking */}
      <SupportedFormatsModal
        isOpen={showFormats}
        onClose={() => setShowFormats(false)}
        onSelectExample={handleSelectExample}
        capabilities={capabilities}
      />
    </>
  );
}
