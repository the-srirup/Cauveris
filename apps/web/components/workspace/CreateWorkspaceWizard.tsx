"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Check,
  ChevronLeft,
  ChevronRight,
  FileArchive,
  Globe,
  Loader2,
  NotebookPen,
  Upload,
} from "lucide-react";
import {
  api,
  INCIDENT_CATEGORIES,
  INCIDENT_ENVIRONMENTS,
  INCIDENT_INTAKE_METHODS,
  INCIDENT_SEVERITIES,
  type IncidentCategory,
  type IncidentEnvironment,
  type IncidentIntakeMethod,
  type IncidentSeverity,
} from "@/lib/api";
import { Badge, Button } from "@/components/ui";
import { WorkspaceShell } from "./WorkspaceShell";

/** The three ways evidence can arrive. */
type SourceKind = "archive" | "source" | "manual";

const QUICK_PRESETS = [
  { label: "PyPI (requests)", value: "pypi:requests@2.32.3", title: "PyPI Intake: requests@2.32.3", system: "pypi-requests" },
  { label: "GitHub (Hello-World)", value: "github:octocat/Hello-World", title: "GitHub Repo: octocat/Hello-World", system: "github-codeload" },
  { label: "npm (lodash)", value: "npm:lodash@4.17.21", title: "npm Package: lodash@4.17.21", system: "node-worker" },
  { label: "crates (serde)", value: "crates:serde@1.0.200", title: "crates.io: serde@1.0.200", system: "rust-crates" },
  { label: "Go (sync)", value: "go:golang.org/x/sync@v0.7.0", title: "Go Module: sync@v0.7.0", system: "go-proxy" },
  { label: "Git clone", value: "git+https://github.com/octocat/Hello-World.git", title: "Git Clone: Hello-World", system: "git-shallow" },
];

const STEPS = [
  { id: 1, title: "Source", hint: "Where the evidence comes from" },
  { id: 2, title: "Details", hint: "What went wrong, and how bad" },
  { id: 3, title: "Review", hint: "Confirm and create" },
] as const;

interface WizardState {
  sourceKind: SourceKind;
  source: string;
  file: File | null;
  title: string;
  description: string;
  systemName: string;
  severity: IncidentSeverity;
  category: IncidentCategory;
  environment: IncidentEnvironment;
  tags: string;
  approximateTime: string;
}

const INITIAL_STATE: WizardState = {
  sourceKind: "archive",
  source: "",
  file: null,
  title: "",
  description: "",
  systemName: "",
  severity: "high",
  category: "detection",
  environment: "warehouse",
  tags: "",
  approximateTime: "",
};

/**
 * The three-step create-an-incident wizard.
 *
 * It replaces a 34 KB modal that collected severity, category and environment
 * and then threw them away — those values now travel with the incident through
 * the API, through the evidence manifest, and into the session package.
 *
 * The wizard asks for everything before creating anything: what the incident
 * is called, what happened, how bad it is, what kind of failure it is, where
 * it happened, and what the evidence is.  Nothing is invented for the
 * operator — the form is explicit about what each field changes downstream.
 */
export function CreateWorkspaceWizard({ initialMode }: { initialMode?: SourceKind | "upload" }) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState(1);
  const [state, setState] = useState<WizardState>(INITIAL_STATE);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileAccept, setFileAccept] = useState(".zip,.tar,.gz,.tgz");

  // A deep link may open the wizard on a specific source type.
  useEffect(() => {
    if (!initialMode) return;
    setState((prev) => ({
      ...prev,
      sourceKind: initialMode === "upload" ? "archive" : initialMode,
    }));
  }, [initialMode]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve(api.getIngestCapabilities?.())
      .then((caps) => {
        if (cancelled || !caps?.supported_archive_extensions?.length) return;
        setFileAccept(caps.supported_archive_extensions.join(","));
      })
      .catch(() => {
        // The fallback accept list is already set.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const update = useCallback(<K extends keyof WizardState>(key: K, value: WizardState[K]) => {
    setState((prev) => ({ ...prev, [key]: value }));
    setError(null);
  }, []);

  const tags = useMemo(
    () =>
      state.tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    [state.tags]
  );

  /** A name suggestion that always stays editable. */
  const suggestTitle = useCallback(() => {
    if (state.title.trim()) return;
    if (state.sourceKind === "source" && state.source.trim()) {
      update("title", `Source Intake: ${state.source.trim()}`);
    } else if (state.sourceKind === "archive" && state.file) {
      update("title", `Uploaded Bundle: ${state.file.name}`);
    }
  }, [state.title, state.sourceKind, state.source, state.file, update]);

  const handlePreset = (preset: (typeof QUICK_PRESETS)[number]) => {
    setState((prev) => ({
      ...prev,
      sourceKind: "source",
      source: preset.value,
      title: prev.title || preset.title,
      systemName: prev.systemName || preset.system,
    }));
    setError(null);
  };

  const handleFile = (file: File | undefined | null) => {
    if (!file) return;
    setState((prev) => ({
      ...prev,
      sourceKind: "archive",
      file,
      title: prev.title || `Uploaded Bundle: ${file.name}`,
    }));
    setError(null);
  };

  const stepOneValid = useMemo(() => {
    if (state.sourceKind === "archive") return Boolean(state.file);
    if (state.sourceKind === "source") return state.source.trim().length > 0;
    return true;
  }, [state.sourceKind, state.file, state.source]);

  const stepTwoValid = state.title.trim().length > 0 && state.description.trim().length > 0;

  const goNext = () => {
    if (step === 1) {
      if (!stepOneValid) {
        setError(
          state.sourceKind === "archive"
            ? "Choose an archive to continue."
            : "Enter a source to continue."
        );
        return;
      }
      suggestTitle();
    }
    if (step === 2) {
      if (!stepTwoValid) {
        setError("A name and a description are both required.");
        return;
      }
    }
    setError(null);
    setStep((s) => Math.min(3, s + 1));
  };

  const submit = async () => {
    if (!stepTwoValid) {
      setError("A name and a description are both required.");
      setStep(2);
      return;
    }
    setIsSubmitting(true);
    setError(null);

    const metadata = {
      title: state.title.trim(),
      description: state.description.trim(),
      system_name: state.systemName.trim() || undefined,
      severity: state.severity,
      category: state.category,
      environment: state.environment,
      tags,
      intake_method: (state.sourceKind === "archive"
        ? "archive"
        : state.sourceKind === "source"
          ? "source"
          : "manual") as IncidentIntakeMethod,
      approximate_time: state.approximateTime || undefined,
    };

    try {
      let incidentId = "";
      let jobId = "";

      if (state.sourceKind === "archive" && state.file) {
        // The single-step canonical upload: the archive and its metadata land
        // in one request, so there is never a half-created incident.
        const uploaded = await api.uploadPackage(state.file, metadata);
        incidentId = uploaded.incident_id;
        jobId = uploaded.job_id ?? "";
      } else if (state.sourceKind === "source" && state.source.trim()) {
        const job = await api.ingestFromSource(state.source.trim(), {
          title: metadata.title,
          description: metadata.description,
          systemName: metadata.system_name,
          severity: metadata.severity,
          category: metadata.category,
          environment: metadata.environment,
          tags: metadata.tags,
          intakeMethod: metadata.intake_method,
          approximateTime: metadata.approximate_time,
        });
        incidentId = job.incident_id;
        jobId = job.job_id;
      } else {
        const created = await api.create(false, metadata);
        incidentId = created.incident_id;
      }

      if (!incidentId) {
        throw new Error("The server did not return an incident id. Nothing was opened.");
      }

      // Hand the work to the loading surface, which waits for the intake to
      // settle before opening the dashboard on the right incident.
      const params = new URLSearchParams({ incident: incidentId });
      if (jobId) params.set("job", jobId);
      router.push(`/workspace/loading?${params.toString()}`);
    } catch (err: unknown) {
      setError(
        err instanceof Error
          ? err.message
          : "The incident could not be created. Nothing was saved."
      );
      setIsSubmitting(false);
    }
  };

  return (
    <WorkspaceShell
      title="New incident"
      subtitle="Three steps. Nothing is created until you confirm."
      backHref="/workspace"
      backLabel="Back to workspace"
      contentClassName="flex-1 flex flex-col justify-center mx-auto w-full max-w-4xl px-4 sm:px-6 py-8 sm:py-12"
    >
      <div className="w-full my-auto">
        <div className="rounded-[var(--radius-xl,12px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] shadow-sm overflow-hidden">
          {/* Wizard Header / Stepper Rail */}
          <div className="border-b border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70 px-4 py-3.5 sm:px-8">
            <ol className="grid grid-cols-3 gap-2 sm:gap-4" aria-label="Wizard progress">
              {STEPS.map((entry) => {
                const isCurrent = entry.id === step;
                const isDone = entry.id < step;
                return (
                  <li key={entry.id} className="flex items-center">
                    <button
                      type="button"
                      onClick={() => (isDone || isCurrent ? setStep(entry.id) : undefined)}
                      disabled={!isDone && !isCurrent}
                      aria-current={isCurrent ? "step" : undefined}
                      className={`w-full flex items-center gap-2.5 sm:gap-3 rounded-[var(--radius-md,6px)] px-2.5 py-1.5 sm:px-3 sm:py-2 text-left transition-colors ${
                        isCurrent
                          ? "bg-[var(--color-accent-subtle)] text-[var(--color-fg-default)] shadow-xs"
                          : isDone
                            ? "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-muted)]"
                            : "text-[var(--color-fg-subtle)] opacity-70"
                      }`}
                    >
                      <span
                        className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                          isCurrent
                            ? "bg-[var(--color-accent)] text-[var(--color-fg-on-emphasis)] shadow-xs"
                            : isDone
                              ? "bg-[var(--color-success-emphasis,#1a7f37)] text-[var(--color-fg-on-emphasis)]"
                              : "border border-[var(--color-border-default)] text-[var(--color-fg-subtle)]"
                        }`}
                      >
                        {isDone ? <Check className="h-3.5 w-3.5" /> : entry.id}
                      </span>
                      <span className="min-w-0">
                        <span className="block text-xs font-medium truncate">{entry.title}</span>
                        <span className="hidden md:block text-[11px] text-[var(--color-fg-subtle)] truncate">
                          {entry.hint}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </div>

          {/* Wizard Content Body */}
          <div className="p-6 sm:p-8 md:p-10 space-y-6">
            {step === 1 && (
              <section aria-labelledby="wizard-step-1" className="space-y-6">
                <div className="space-y-1">
                  <h2 id="wizard-step-1" className="text-lg font-semibold tracking-tight text-[var(--color-fg-default)]">
                    Where is the evidence?
                  </h2>
                  <p className="text-xs sm:text-sm text-[var(--color-fg-muted)]">
                    Pick one. You can add more evidence after the incident exists.
                  </p>
                </div>

                <div className="grid gap-3.5 sm:grid-cols-3">
                  {(
                    [
                      {
                        kind: "archive" as const,
                        icon: Upload,
                        title: "Archive",
                        line: "A .zip of logs, config and telemetry.",
                        note: "Unpacked, checksummed and inventoried on arrival.",
                      },
                      {
                        kind: "source" as const,
                        icon: Globe,
                        title: "Registry or Git",
                        line: "A GitHub repo, an npm or PyPI package, or a URL.",
                        note: "Cauveris fetches and unpacks it for you.",
                      },
                      {
                        kind: "manual" as const,
                        icon: NotebookPen,
                        title: "Manual",
                        line: "No evidence yet.",
                        note: "An empty investigation you add files to later.",
                      },
                    ]
                  ).map((option) => {
                    const isSelected = state.sourceKind === option.kind;
                    const Icon = option.icon;
                    return (
                      <button
                        key={option.kind}
                        type="button"
                        onClick={() => update("sourceKind", option.kind)}
                        aria-pressed={isSelected}
                        className={`flex flex-col gap-2 rounded-[var(--radius-lg,8px)] border p-4 sm:p-5 text-left transition-all duration-100 ${
                          isSelected
                            ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)] ring-1 ring-[var(--color-accent)] shadow-xs"
                            : "border-[var(--color-border-default)] bg-[var(--color-canvas)]/40 hover:border-[var(--color-border-strong)] hover:bg-[var(--color-canvas)]"
                        }`}
                      >
                        <Icon
                          className={`h-5 w-5 ${
                            isSelected
                              ? "text-[var(--color-accent-fg)]"
                              : "text-[var(--color-fg-subtle)]"
                          }`}
                        />
                        <div className="space-y-1">
                          <span className="block text-sm font-semibold text-[var(--color-fg-default)]">
                            {option.title}
                          </span>
                          <span className="block text-xs text-[var(--color-fg-default)] leading-relaxed">
                            {option.line}
                          </span>
                          <span className="block text-[11px] text-[var(--color-fg-subtle)] leading-normal">
                            {option.note}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>

                {state.sourceKind === "archive" && (
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
                        handleFile(e.dataTransfer.files?.[0]);
                      }}
                      className={`rounded-[var(--radius-lg,8px)] border-2 border-dashed p-8 sm:p-10 text-center transition-colors ${
                        isDragging
                          ? "border-[var(--color-accent)] bg-[var(--color-accent-subtle)]"
                          : "border-[var(--color-border-default)] bg-[var(--color-canvas)]/30 hover:border-[var(--color-border-strong)]"
                      }`}
                    >
                      <FileArchive className="mx-auto h-8 w-8 text-[var(--color-fg-subtle)]" />
                      <p className="mt-3 text-sm font-medium text-[var(--color-fg-default)]">
                        {state.file ? state.file.name : "Drop an evidence archive here"}
                      </p>
                      {state.file ? (
                        <p className="mt-1 text-xs text-[var(--color-fg-muted)]">
                          {(state.file.size / 1024).toFixed(1)} KB — click Choose a file to replace it
                        </p>
                      ) : (
                        <p className="mx-auto mt-1 max-w-sm text-xs text-[var(--color-fg-muted)]">
                          A <code className="font-mono text-[var(--color-accent-fg)]">.zip</code> bundle. Single evidence files
                          work too, though an archive is preferred.
                        </p>
                      )}
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept={fileAccept}
                        className="sr-only"
                        aria-label="Choose an evidence archive"
                        onChange={(e) => {
                          handleFile(e.target.files?.[0]);
                          e.target.value = "";
                        }}
                      />
                      <Button
                        variant="secondary"
                        size="md"
                        className="mt-4"
                        onClick={() => fileInputRef.current?.click()}
                      >
                        Choose a file
                      </Button>
                    </div>
                  </div>
                )}

                {state.sourceKind === "source" && (
                  <div className="space-y-4 rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas)]/30 p-5">
                    <div>
                      <label
                        htmlFor="wizard-source"
                        className="block text-xs font-medium text-[var(--color-fg-default)]"
                      >
                        Source Package or Repository
                      </label>
                      <input
                        id="wizard-source"
                        type="text"
                        value={state.source}
                        onChange={(e) => update("source", e.target.value)}
                        placeholder="github:owner/repo, npm:lodash@4.17.21, or https://..."
                        className={INPUT_CLASS}
                      />
                      <p className="mt-1.5 text-xs text-[var(--color-fg-muted)]">
                        Cauveris fetches the package, extracts it, and indexes what it finds.
                      </p>
                    </div>

                    <div className="pt-2 border-t border-[var(--color-border-muted)]">
                      <p className="text-xs font-medium text-[var(--color-fg-default)] mb-2">Quick Presets</p>
                      <div className="flex flex-wrap gap-2">
                        {QUICK_PRESETS.map((preset) => (
                          <button
                            key={preset.value}
                            type="button"
                            onClick={() => handlePreset(preset)}
                            className="rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default)] bg-[var(--color-canvas-default)] px-2.5 py-1 text-xs text-[var(--color-fg-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-fg-default)]"
                          >
                            {preset.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {state.sourceKind === "manual" && (
                  <div className="rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas)]/30 p-5 text-center">
                    <NotebookPen className="mx-auto h-7 w-7 text-[var(--color-fg-subtle)] mb-2" />
                    <p className="text-sm font-medium text-[var(--color-fg-default)]">Starting Without Initial Archive</p>
                    <p className="mx-auto mt-1 max-w-md text-xs text-[var(--color-fg-muted)] leading-relaxed">
                      This will initialize an empty investigation workspace. You can drag and drop telemetry, core dumps, or logs into the Evidence Vault at any time later.
                    </p>
                  </div>
                )}
              </section>
            )}

            {step === 2 && (
              <section aria-labelledby="wizard-step-2" className="space-y-6">
                <div className="space-y-1">
                  <h2 id="wizard-step-2" className="text-lg font-semibold tracking-tight text-[var(--color-fg-default)]">
                    What happened?
                  </h2>
                  <p className="text-xs sm:text-sm text-[var(--color-fg-muted)]">
                    These answers travel with the incident — into its manifest and into any session you save later.
                  </p>
                </div>

                <div className="space-y-5">
                  <Field
                    id="wizard-title"
                    label="Incident name"
                    required
                    hint="How this investigation is listed everywhere. You can change it later."
                  >
                    <input
                      id="wizard-title"
                      type="text"
                      value={state.title}
                      onChange={(e) => update("title", e.target.value)}
                      placeholder="Warehouse AMR thermal anomaly"
                      className={INPUT_CLASS}
                    />
                  </Field>

                  <Field
                    id="wizard-description"
                    label="What happened"
                    required
                    hint="The observed behaviour. This is what the investigation is asked to explain."
                  >
                    <textarea
                      id="wizard-description"
                      value={state.description}
                      onChange={(e) => update("description", e.target.value)}
                      rows={4}
                      placeholder="The robot stopped mid-pick at bay 7 and vented coolant while idle."
                      className={`${INPUT_CLASS} h-auto resize-y py-2.5 leading-relaxed`}
                    />
                  </Field>

                  <Field
                    id="wizard-system"
                    label="System"
                    hint="The robot, vehicle or service this happened to."
                  >
                    <input
                      id="wizard-system"
                      type="text"
                      value={state.systemName}
                      onChange={(e) => update("systemName", e.target.value)}
                      placeholder="warehouse-amr-07"
                      className={`${INPUT_CLASS} font-mono`}
                    />
                  </Field>

                  <div className="grid gap-4 sm:grid-cols-3">
                    <SelectField
                      id="wizard-severity"
                      label="Severity"
                      hint="How bad the impact was."
                      value={state.severity}
                      options={INCIDENT_SEVERITIES.map((value) => ({ value, label: value }))}
                      onChange={(value) => update("severity", value as IncidentSeverity)}
                    />
                    <SelectField
                      id="wizard-category"
                      label="Category"
                      hint="What kind of failure it was."
                      value={state.category}
                      options={INCIDENT_CATEGORIES.map((value) => ({ value, label: value }))}
                      onChange={(value) => update("category", value as IncidentCategory)}
                    />
                    <SelectField
                      id="wizard-environment"
                      label="Environment"
                      hint="Where the system was running."
                      value={state.environment}
                      options={INCIDENT_ENVIRONMENTS.map((value) => ({ value, label: value }))}
                      onChange={(value) => update("environment", value as IncidentEnvironment)}
                    />
                  </div>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field
                      id="wizard-tags"
                      label="Tags"
                      hint="Comma-separated. Useful for filtering later."
                    >
                      <input
                        id="wizard-tags"
                        type="text"
                        value={state.tags}
                        onChange={(e) => update("tags", e.target.value)}
                        placeholder="thermal, coolant, bay-7"
                        className={INPUT_CLASS}
                      />
                    </Field>

                    <Field
                      id="wizard-time"
                      label="When did it happen?"
                      hint="Leave blank if you do not know."
                    >
                      <input
                        id="wizard-time"
                        type="datetime-local"
                        value={state.approximateTime}
                        onChange={(e) => update("approximateTime", e.target.value)}
                        className={INPUT_CLASS}
                      />
                    </Field>
                  </div>
                </div>
              </section>
            )}

            {step === 3 && (
              <section aria-labelledby="wizard-step-3" className="space-y-6">
                <div className="space-y-1">
                  <h2 id="wizard-step-3" className="text-lg font-semibold tracking-tight text-[var(--color-fg-default)]">
                    Ready to create
                  </h2>
                  <p className="text-xs sm:text-sm text-[var(--color-fg-muted)]">
                    Here is exactly what will exist. Creating an incident does not start the pipeline — you press Start on the dashboard.
                  </p>
                </div>

                <dl className="divide-y divide-[var(--color-border-default)] overflow-hidden rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default)] bg-[var(--color-canvas)]/40">
                  <SummaryRow label="Name" value={state.title} />
                  <SummaryRow label="Description" value={state.description} />
                  {state.systemName && <SummaryRow label="System" value={state.systemName} mono />}
                  <SummaryRow
                    label="Source"
                    value={
                      state.sourceKind === "archive"
                        ? state.file
                          ? state.file.name
                          : "—"
                        : state.sourceKind === "source"
                          ? state.source
                          : "Manual — no evidence yet"
                    }
                    mono={state.sourceKind !== "manual"}
                  />
                  <SummaryRow
                    label="Severity"
                    value={<Badge variant="default" size="sm">{state.severity}</Badge>}
                  />
                  <SummaryRow label="Category" value={state.category} mono />
                  <SummaryRow label="Environment" value={state.environment} mono />
                  {tags.length > 0 && (
                    <SummaryRow
                      label="Tags"
                      value={
                        <span className="flex flex-wrap gap-1">
                          {tags.map((tag) => (
                            <Badge key={tag} variant="default" size="sm">
                              {tag}
                            </Badge>
                          ))}
                        </span>
                      }
                    />
                  )}
                  {state.approximateTime && (
                    <SummaryRow label="Approximate time" value={state.approximateTime} mono />
                  )}
                </dl>

                <p className="text-xs text-[var(--color-fg-muted)]">
                  Intake method:{" "}
                  <code className="font-mono text-[var(--color-accent-fg)]">
                    {state.sourceKind === "archive"
                      ? "archive"
                      : state.sourceKind === "source"
                        ? "source"
                        : "manual"}
                  </code>
                  . You can save this investigation as a session package at any time and resume it later.
                </p>
              </section>
            )}

            {error && (
              <div
                className="flex items-start gap-2.5 rounded-[var(--radius-md,6px)] border border-[var(--color-danger-muted)] bg-[var(--color-danger-subtle)] px-4 py-3 text-xs text-[var(--color-danger-fg)]"
                role="alert"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}
          </div>

          {/* Wizard Action Footer */}
          <div className="border-t border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/70 px-6 py-4 sm:px-8 flex items-center justify-between gap-4">
            {step > 1 ? (
              <Button
                variant="ghost"
                size="md"
                onClick={() => setStep((s) => Math.max(1, s - 1))}
                leadingIcon={<ChevronLeft className="h-4 w-4" />}
              >
                Back
              </Button>
            ) : (
              <div />
            )}

            {step < 3 ? (
              <Button
                variant="primary"
                size="md"
                onClick={goNext}
                trailingIcon={<ChevronRight className="h-4 w-4" />}
              >
                Continue
              </Button>
            ) : (
              <Button
                variant="primary"
                size="md"
                onClick={() => void submit()}
                loading={isSubmitting}
                loadingText="Creating..."
              >
                Create & open workspace
              </Button>
            )}
          </div>
        </div>
      </div>
    </WorkspaceShell>
  );
}

const INPUT_CLASS =
  "mt-1.5 h-10 w-full rounded-[var(--radius-sm,4px)] border border-[var(--color-border-default)] bg-[var(--color-canvas)] px-3 text-sm text-[var(--color-fg-default)] placeholder:text-[var(--color-fg-subtle)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] transition-colors";

function Field({
  id,
  label,
  hint,
  required,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-[var(--color-fg-default)]">
        {label}
        {required && (
          <span className="ml-1 text-[var(--color-danger-fg)]" aria-hidden="true">
            *
          </span>
        )}
        {required && <span className="sr-only"> (required)</span>}
      </label>
      {children}
      {hint && <p className="mt-1.5 text-xs text-[var(--color-fg-muted)]">{hint}</p>}
    </div>
  );
}

function SelectField({
  id,
  label,
  hint,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  hint?: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-[var(--color-fg-default)]">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`${INPUT_CLASS} cursor-pointer`}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {hint && <p className="mt-1.5 text-xs text-[var(--color-fg-muted)]">{hint}</p>}
    </div>
  );
}

function SummaryRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="w-40 flex-shrink-0 text-xs font-medium text-[var(--color-fg-muted)]">{label}</dt>
      <dd
        className={`min-w-0 flex-1 break-words text-sm text-[var(--color-fg-default)] ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </dd>
    </div>
  );
}

export default CreateWorkspaceWizard;
