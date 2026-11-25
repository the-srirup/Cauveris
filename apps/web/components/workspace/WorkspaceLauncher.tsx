"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  FileArchive,
  FileText,
  History,
  Loader2,
  Plus,
  Sparkles,
  Upload,
} from "lucide-react";
import { api, type Incident } from "@/lib/api";
import { Button } from "@/components/ui";
import { Badge } from "@/components/ui";
import { useActiveIncident } from "@/lib/useIncident";
import { WorkspaceShell } from "./WorkspaceShell";

/**
 * The workspace launcher — the screen an operator sees after signing in.
 *
 * Every incident-lifecycle action lives here and nowhere else: create, resume
 * a saved session, open a recent investigation, load the sample benchmark.
 * The dashboard owns *investigating* an incident; this screen owns *opening*
 * one.
 */
export function WorkspaceLauncher() {
  const router = useRouter();
  const { setIncidentId } = useActiveIncident();
  const sessionFileInputRef = useRef<HTMLInputElement>(null);

  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [isLoadingRecents, setIsLoadingRecents] = useState(true);
  const [isCreatingSample, setIsCreatingSample] = useState(false);
  const [isImportingSession, setIsImportingSession] = useState(false);
  const [isDraggingSession, setIsDraggingSession] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ensure view starts from top on every navigation
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  const loadRecents = useCallback(async () => {
    setIsLoadingRecents(true);
    try {
      const result = await api.list();
      setIncidents(result.incidents ?? []);
      setError(null);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "The recent investigations could not be loaded."
      );
    } finally {
      setIsLoadingRecents(false);
    }
  }, []);

  useEffect(() => {
    void loadRecents();
  }, [loadRecents]);

  /**
   * Open an incident on the dashboard.
   */
  const openIncident = (incidentId: string) => {
    setIncidentId(incidentId);
    router.push("/");
  };

  const loadSample = async () => {
    setIsCreatingSample(true);
    setError(null);
    try {
      const created = await api.create(true);
      openIncident(created.incident_id);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "The sample benchmark could not be loaded."
      );
      setIsCreatingSample(false);
    }
  };

  const handleSessionFile = async (file: File | undefined | null) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("A session package must be a valid .zip archive exported from Cauveris.");
      return;
    }

    setIsImportingSession(true);
    setError(null);
    try {
      const result = await api.importSession(file);
      openIncident(result.incident_id);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "The session package could not be restored."
      );
    } finally {
      setIsImportingSession(false);
    }
  };

  const recents = incidents.slice(0, 8);

  return (
    <WorkspaceShell
      title="Open a workspace"
      subtitle="Create an incident, resume a saved session, or pick up where you left off."
      contentClassName="flex-1 mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8 py-8 sm:py-10 space-y-9"
    >
      {/* Hidden file input for Session Package import */}
      <input
        ref={sessionFileInputRef}
        type="file"
        accept=".zip,application/zip"
        className="sr-only"
        aria-label="Choose a session package file"
        onChange={(e) => {
          void handleSessionFile(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      {/* --- Studio Overview Banner --------------------------------------- */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 pb-6 border-b border-[var(--color-border-default)]">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-[var(--color-fg-default)]">
            Workspace
          </h1>
          <p className="mt-1 text-xs sm:text-sm text-[var(--color-fg-muted)]">
            Open recent investigations, launch a new incident, or restore a saved session package.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] text-[var(--color-fg-muted)]">
            <span className="h-2 w-2 rounded-full bg-[var(--color-success-emphasis,#1a7f37)]" />
            Systems Ready
          </span>
        </div>
      </div>

      {error && (
        <div
          className="rounded-[var(--radius-md,6px)] border border-[var(--color-danger-muted)] bg-[var(--color-danger-subtle)] px-4 py-3 text-xs text-[var(--color-danger-fg)]"
          role="alert"
        >
          {error}
        </div>
      )}

      {/* --- Launchpad Actions: The 3 Core Operations --------------------- */}
      <section aria-labelledby="workspace-actions-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <h2
            id="workspace-actions-heading"
            className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)]"
          >
            Start an Investigation
          </h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Card 1: New Incident (Primary CTA) */}
          <button
            type="button"
            onClick={() => router.push("/workspace/new")}
            className="group relative flex flex-col justify-between rounded-[var(--radius-xl,12px)] border border-[var(--color-accent-muted)] bg-[var(--color-canvas-default)] p-6 text-left shadow-sm transition-all duration-150 hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-accent)] hover:shadow-md"
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-lg,8px)] bg-[var(--color-accent)] text-[var(--color-fg-on-emphasis)] shadow-xs">
                  <Plus className="h-5 w-5" />
                </span>
                <Badge variant="primary" size="sm">Primary</Badge>
              </div>
              <div>
                <h3 className="text-base font-semibold text-[var(--color-fg-default)] group-hover:text-[var(--color-accent-fg)] transition-colors">
                  New incident
                </h3>
                <p className="mt-1 text-xs sm:text-sm text-[var(--color-fg-muted)] leading-relaxed">
                  Bring in an evidence archive (.zip), connect a Git or registry repository, or create an empty investigation.
                </p>
              </div>
            </div>
            <div className="mt-5 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-accent-fg)]">
              <span>Create incident</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-1" />
            </div>
          </button>

          {/* Card 2: Load Sample Benchmark */}
          <button
            type="button"
            onClick={loadSample}
            disabled={isCreatingSample}
            aria-label="Load golden incident"
            className="group relative flex flex-col justify-between rounded-[var(--radius-xl,12px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] p-6 text-left shadow-sm transition-all duration-150 hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)] hover:shadow-md disabled:cursor-not-allowed disabled:opacity-60"
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-muted)] text-[var(--color-fg-default)]">
                  {isCreatingSample ? (
                    <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent)]" />
                  ) : (
                    <Sparkles className="h-5 w-5" />
                  )}
                </span>
                <Badge variant="muted" size="sm">Ground Truth</Badge>
              </div>
              <div>
                <h3 className="text-base font-semibold text-[var(--color-fg-default)]">
                  Load sample benchmark
                </h3>
                <p className="mt-1 text-xs sm:text-sm text-[var(--color-fg-muted)] leading-relaxed">
                  A fully worked warehouse AMR thermal failure with known ground truth — explore without importing files.
                </p>
              </div>
            </div>
            <div className="mt-5 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-fg-default)] group-hover:text-[var(--color-accent-fg)] transition-colors">
              <span>{isCreatingSample ? "Loading sample..." : "Launch benchmark"}</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-1" />
            </div>
          </button>

          {/* Card 3: Resume Saved Session Package */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDraggingSession(true);
            }}
            onDragLeave={() => setIsDraggingSession(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDraggingSession(false);
              void handleSessionFile(e.dataTransfer.files?.[0]);
            }}
            onClick={() => sessionFileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                sessionFileInputRef.current?.click();
              }
            }}
            aria-label="Resume saved session package (.zip)"
            className={`group relative flex flex-col justify-between rounded-[var(--radius-xl,12px)] border p-6 text-left shadow-sm cursor-pointer transition-all duration-150 ${
              isDraggingSession
                ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
                : "border-[var(--color-border-default)] bg-[var(--color-canvas-default)] hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)] hover:shadow-md"
            }`}
          >
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="flex h-10 w-10 items-center justify-center rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-muted)] text-[var(--color-fg-default)]">
                  {isImportingSession ? (
                    <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent)]" />
                  ) : (
                    <History className="h-5 w-5" />
                  )}
                </span>
                <Badge variant="muted" size="sm">.zip Package</Badge>
              </div>
              <div>
                <h3 className="text-base font-semibold text-[var(--color-fg-default)]">
                  Resume saved session
                </h3>
                <p className="mt-1 text-xs sm:text-sm text-[var(--color-fg-muted)] leading-relaxed">
                  Restore an exported session package with complete evidence, stage progression, and verified patch state.
                </p>
              </div>
            </div>
            <div className="mt-5 flex items-center gap-1.5 text-xs font-semibold text-[var(--color-fg-default)] group-hover:text-[var(--color-accent-fg)] transition-colors">
              <Upload className="h-3.5 w-3.5" />
              <span>{isImportingSession ? "Restoring package..." : isDraggingSession ? "Drop .zip here" : "Choose .zip or drop here"}</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform duration-150 group-hover:translate-x-1 ml-auto" />
            </div>
          </div>
        </div>
      </section>

      {/* --- Recent Investigations (Full Width Stage) -------------------- */}
      <section aria-labelledby="workspace-recent-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <h2
              id="workspace-recent-heading"
              className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)]"
            >
              Recent Investigations
            </h2>
            <Badge variant="muted" size="sm">
              {recents.length}
            </Badge>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void loadRecents()}
            aria-label="Refresh recent investigations"
          >
            Refresh
          </Button>
        </div>

        <div className="overflow-hidden rounded-[var(--radius-xl,12px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] shadow-sm">
          {isLoadingRecents ? (
            <div className="flex items-center justify-center gap-3 px-6 py-12 text-sm text-[var(--color-fg-muted)]">
              <Loader2 className="h-5 w-5 animate-spin text-[var(--color-accent)]" />
              <span>Loading recent investigations...</span>
            </div>
          ) : recents.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
              <FileText className="h-10 w-10 text-[var(--color-fg-subtle)] stroke-[1.5] mb-2" />
              <p className="text-sm font-medium text-[var(--color-fg-default)]">
                No investigations recorded yet
              </p>
              <p className="mt-1 text-xs text-[var(--color-fg-muted)] max-w-sm">
                Create a new incident from an evidence archive, or load the sample benchmark above to get started.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[var(--color-border-default)]">
              {recents.map((incident) => (
                <button
                  key={incident.id}
                  type="button"
                  onClick={() => openIncident(incident.id)}
                  className="group flex w-full items-center gap-4 px-5 py-4 text-left transition-colors duration-100 hover:bg-[var(--color-canvas-subtle)] focus-visible:outline-none focus-visible:bg-[var(--color-canvas-subtle)]"
                >
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[var(--radius-md,6px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-muted)] text-[var(--color-fg-muted)] group-hover:border-[var(--color-accent-muted)] group-hover:text-[var(--color-accent-fg)] transition-colors">
                    <FileText className="h-4.5 w-4.5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-semibold text-[var(--color-fg-default)] group-hover:text-[var(--color-accent-fg)] transition-colors">
                        {incident.title}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 font-mono text-xs text-[var(--color-fg-subtle)]">
                      <span>{incident.id}</span>
                      {incident.environment && (
                        <>
                          <span>•</span>
                          <span className="capitalize">{incident.environment}</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    {incident.severity && (
                      <Badge
                        variant={
                          incident.severity === "critical"
                            ? "danger"
                            : incident.severity === "high"
                              ? "warning"
                              : "default"
                        }
                        size="sm"
                      >
                        {incident.severity}
                      </Badge>
                    )}
                    <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-sm,4px)] text-[var(--color-fg-subtle)] group-hover:text-[var(--color-accent-fg)] group-hover:translate-x-0.5 transition-all">
                      <ArrowRight className="h-4 w-4" />
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* --- Technical Guidance & Specifications Shelf ------------------ */}
      <section aria-labelledby="workspace-guidelines-heading" className="pt-6 border-t border-[var(--color-border-default)]">
        <h2
          id="workspace-guidelines-heading"
          className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-subtle)] mb-4"
        >
          Intake Formats & Integrity Specifications
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] p-5 shadow-xs">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[var(--color-fg-default)]">
              <FileArchive className="h-4.5 w-4.5 text-[var(--color-accent-fg)]" />
              Supported Evidence Sources
            </div>
            <ul className="mt-3 space-y-2 text-xs text-[var(--color-fg-muted)] leading-relaxed">
              <li>
                <strong className="font-medium text-[var(--color-fg-default)]">Evidence archives:</strong>{" "}
                <code className="font-mono text-[11px] px-1 py-0.5 rounded bg-[var(--color-canvas-muted)]">.zip</code>,{" "}
                <code className="font-mono text-[11px] px-1 py-0.5 rounded bg-[var(--color-canvas-muted)]">.tar.gz</code> logs, MCAP telemetry, and configuration bundles.
              </li>
              <li>
                <strong className="font-medium text-[var(--color-fg-default)]">Registries & Git:</strong>{" "}
                GitHub repository branches, npm packages, PyPI distributions, or Go modules.
              </li>
            </ul>
          </div>

          <div className="rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] p-5 shadow-xs">
            <div className="flex items-center gap-2.5 text-sm font-semibold text-[var(--color-fg-default)]">
              <History className="h-4.5 w-4.5 text-[var(--color-success-fg,#1a7f37)]" />
              Session Package Scope
            </div>
            <ul className="mt-3 space-y-2 text-xs text-[var(--color-fg-muted)] leading-relaxed">
              <li>Complete evidence bundle preserved with cryptographic SHA-256 checksums.</li>
              <li>Full pipeline stage progression, diagnostic reports, and verified patch artifacts.</li>
            </ul>
          </div>
        </div>
      </section>
    </WorkspaceShell>
  );
}

export default WorkspaceLauncher;
