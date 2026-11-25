"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useActiveIncident } from "@/lib/useIncident";
import { Button } from "@/components/ui";
import { Badge } from "@/components/ui";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";

/** How long a source ingest may run before we stop waiting for it. */
const INGEST_DEADLINE_MS = 10 * 60 * 1000;

const TERMINAL_STATUSES = ["completed", "failed", "dead_letter", "cancelled"];

/** What a finished intake job reports back. */
interface IngestJobResult {
  incident_id?: string;
  evidence_count?: number;
  warnings?: string[];
}

interface LoadState {
  phase: "waiting" | "working" | "done" | "failed";
  message: string;
  detail?: string;
}

/**
 * The screen between "Create" and the dashboard.
 *
 * Creating an incident is not always instant: a source ingest fetches and
 * unpacks a package, and a session import rehydrates an entire workspace.
 * This page waits for that work to finish and then hands focus to the
 * dashboard — so the operator never lands on a dashboard for an incident that
 * is still being built.
 */
function WorkspaceLoadingRoute() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { setIncidentId } = useActiveIncident();

  const incidentId = searchParams.get("incident") ?? "";
  const jobId = searchParams.get("job") ?? "";

  const [state, setState] = useState<LoadState>({
    phase: "waiting",
    message: incidentId
      ? "Opening your workspace..."
      : "Preparing your workspace...",
  });
  const [summary, setSummary] = useState<{
    evidenceCount?: number;
    warnings?: string[];
  } | null>(null);

  const hasNavigated = useRef(false);

  /** Move to the dashboard once, and only once. */
  const openDashboard = useCallback(
    (id: string) => {
      if (hasNavigated.current) return;
      hasNavigated.current = true;
      setIncidentId(id);
      router.replace("/");
    },
    [router, setIncidentId]
  );

  const openDashboardRef = useRef(openDashboard);
  useEffect(() => {
    openDashboardRef.current = openDashboard;
  }, [openDashboard]);

  useEffect(() => {
    if (!incidentId) {
      setState({
        phase: "failed",
        message: "No incident was created.",
        detail: "Start again from the workspace launcher.",
      });
      return;
    }

    let cancelled = false;

    const run = async () => {
      if (!jobId) {
        // Nothing to wait for — the incident already exists.
        setState({
          phase: "working",
          message: "Opening your workspace...",
        });
        await new Promise((resolve) => setTimeout(resolve, 400));
        if (!cancelled) openDashboardRef.current(incidentId);
        return;
      }

      setState({
        phase: "working",
        message: "Fetching and unpacking the source package...",
      });

      const deadline = Date.now() + INGEST_DEADLINE_MS;
      let status = "running";
      let result: IngestJobResult | null = null;
      let jobError: string | null = null;

      while (!cancelled && Date.now() < deadline) {
        try {
          const polled = await api.getIngestJob(jobId);
          status = polled.status;
          result = polled.result ?? null;
          jobError = polled.error ?? null;
        } catch (err: unknown) {
          if (cancelled) return;
          setState({
            phase: "failed",
            message: "The intake job could not be read.",
            detail:
              err instanceof Error ? err.message : "The server did not answer the status check.",
          });
          return;
        }

        if (TERMINAL_STATUSES.includes(status)) break;

        setState({
          phase: "working",
          message: "Extracting and indexing package artifacts...",
        });
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }

      if (cancelled) return;

      if (status !== "completed") {
        setState({
          phase: "failed",
          message: "The source intake did not finish.",
          detail:
            jobError ||
            `The intake job ended with status "${status}". The incident exists, but its evidence is incomplete.`,
        });
        return;
      }

      setSummary({
        evidenceCount: result?.evidence_count,
        warnings: result?.warnings,
      });
      setState({
        phase: "done",
        message: "Your workspace is ready.",
      });
      await new Promise((resolve) => setTimeout(resolve, 600));
      openDashboardRef.current(result?.incident_id || incidentId);
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [incidentId, jobId]);

  return (
    <WorkspaceShell title="Preparing your workspace" subtitle="This can take a moment for large packages.">
      <div className="mx-auto max-w-xl">
        <div className="rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] p-6">
          <div className="flex items-start gap-3">
            {state.phase === "failed" ? (
              <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--color-danger-fg)]" />
            ) : state.phase === "done" ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5 flex-shrink-0 text-[var(--color-success-fg)]" />
            ) : (
              <Loader2 className="mt-0.5 h-5 w-5 flex-shrink-0 animate-spin text-[var(--color-accent-fg)]" />
            )}

            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-[var(--color-fg-default)]">{state.message}</p>
              {state.detail && (
                <p className="mt-1.5 text-xs text-[var(--color-fg-muted)]">{state.detail}</p>
              )}

              {summary?.evidenceCount !== undefined && (
                <p className="mt-3">
                  <Badge variant="default" size="sm">
                    {summary.evidenceCount} evidence item
                    {summary.evidenceCount === 1 ? "" : "s"}
                  </Badge>
                </p>
              )}

              {summary?.warnings && summary.warnings.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs text-[var(--color-attention-fg)]">
                  {summary.warnings.map((warning, index) => (
                    <li key={index} className="flex items-start gap-1.5">
                      <AlertCircle className="mt-0.5 h-3 w-3 flex-shrink-0" />
                      <span>{warning}</span>
                    </li>
                  ))}
                </ul>
              )}

              {incidentId && (
                <p className="mt-3 font-mono text-[11px] text-[var(--color-fg-subtle)]">
                  {incidentId}
                </p>
              )}
            </div>
          </div>

          {state.phase === "failed" && (
            <div className="mt-5 flex gap-2">
              <Button variant="primary" size="md" onClick={() => router.push("/workspace")}>
                Back to workspace
              </Button>
              {incidentId && (
                <Button variant="secondary" size="md" onClick={() => openDashboard(incidentId)}>
                  Open anyway
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </WorkspaceShell>
  );
}

export default function WorkspaceLoadingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-[var(--color-canvas)]">
          <Loader2 className="h-6 w-6 animate-spin text-[var(--color-accent-fg)]" />
        </div>
      }
    >
      <WorkspaceLoadingRoute />
    </Suspense>
  );
}
