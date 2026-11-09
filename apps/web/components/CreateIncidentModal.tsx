"use client";

import { useState, useEffect, useRef, useId } from "react";
import { createPortal } from "react-dom";
import { tv } from "tailwind-variants";
import {
  X,
  Zap,
  Loader2,
  AlertCircle,
  CheckCircle,
  Globe,
  Upload,
  FileText,
  HelpCircle,
  PackageCheck,
  ChevronDown,
  ChevronUp,
  FileCode,
  ShieldCheck,
  ArrowRight,
  Bot,
  Layers,
  Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button, Input, Select, Badge } from "./ui";
import { useShell } from "@/lib/useShell";
import { useRouter } from "next/navigation";
import { SupportedFormatsModal } from "./SupportedFormatsModal";

const modalStyles = tv({
  base: `
    fixed inset-0 z-[110] flex items-center justify-center p-3 sm:p-6
    bg-black/75 backdrop-blur-xs
    animate-fade-in
  `,
});

const panelStyles = tv({
  base: `
    relative w-full max-w-2xl rounded-[var(--radius-lg,8px)] border border-[var(--color-border-default,#27272a)]
    bg-[var(--color-canvas-inset,#09090b)] shadow-2xl
    overflow-hidden flex flex-col max-h-[90vh] my-auto
    animate-scale-in text-xs
  `,
});

const headerStyles = tv({
  base: `
    flex items-center gap-3 px-6 py-4 border-b border-[var(--color-border-default,#27272a)]
    bg-[var(--color-canvas-subtle,#18181b)] flex-shrink-0
  `,
});

const contentStyles = tv({
  base: `
    px-6 py-5 space-y-5 overflow-y-auto flex-1 min-h-0 overscroll-contain bg-[var(--color-canvas-inset,#09090b)]
  `,
});

const footerStyles = tv({
  base: `
    flex items-center justify-between gap-3 px-6 py-3.5 border-t border-[var(--color-border-default,#27272a)]
    bg-[var(--color-canvas-subtle,#18181b)] flex-shrink-0
  `,
});

const footerHintStyles = tv({
  base: `
    text-[11px] text-[var(--color-fg-muted,#71717a)] self-center
  `,
});

const fieldStyles = tv({
  base: `
    space-y-1.5
  `,
});

const sectionDividerStyles = tv({
  base: `
    flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted,#a1a1aa)]
    py-1.5 border-b border-[var(--color-border-default,#27272a)]/60
  `,
});

const EVIDENCE_ACCEPT_EXTENSIONS = ".json,.jsonl,.ndjson,.csv,.yaml,.yml,.toml,.ini,.log,.txt,.md,.mcap,.bag";
const FALLBACK_FILE_ACCEPT =
  ".zip,.tar,.tar.gz,.tgz,.tar.bz2,.tbz2,.tar.xz,.txz,.gz,.bz2,.xz," + EVIDENCE_ACCEPT_EXTENSIONS;

export type IntakeMode = "source" | "upload" | "manual";

export interface CreateIncidentModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialMode?: IntakeMode;
  onSuccess?: (incidentId: string) => void;
}

const QUICK_PRESETS = [
  { label: "PyPI (requests)", value: "pypi:requests@2.32.3", title: "PyPI Intake: requests@2.32.3", system: "pypi-requests" },
  { label: "GitHub (Hello-World)", value: "github:octocat/Hello-World", title: "GitHub Repo: octocat/Hello-World", system: "github-codeload" },
  { label: "npm (lodash)", value: "npm:lodash@4.17.21", title: "npm Package: lodash@4.17.21", system: "node-worker" },
  { label: "crates (serde)", value: "crates:serde@1.0.200", title: "crates.io: serde@1.0.200", system: "rust-crates" },
  { label: "Go (sync)", value: "go:golang.org/x/sync@v0.7.0", title: "Go Module: sync@v0.7.0", system: "go-proxy" },
  { label: "Git clone", value: "git+https://github.com/octocat/Hello-World.git", title: "Git Clone: Hello-World", system: "git-shallow" },
];

export function CreateIncidentModal({
  isOpen,
  onClose,
  initialMode = "source",
  onSuccess,
}: CreateIncidentModalProps) {
  const { addActivity } = useShell();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [createdIncidentId, setCreatedIncidentId] = useState<string | null>(null);

  // Intake Mode Selector
  const [intakeMode, setIntakeMode] = useState<IntakeMode>(initialMode);
  const [showFormatsModal, setShowFormatsModal] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const [formData, setFormData] = useState({
    name: "",
    description: "",
    severity: "high" as "critical" | "high" | "medium" | "low",
    category: "detection" as "detection" | "navigation" | "planning" | "control" | "communication" | "other",
    robotId: "",
    environment: "warehouse" as "warehouse" | "outdoor" | "lab" | "simulation" | "other",
    tags: "",
    source: "",
    evidenceFiles: [] as File[],
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [fileAccept, setFileAccept] = useState<string>(FALLBACK_FILE_ACCEPT);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Fetch capabilities for file picker accept list
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    try {
      Promise.resolve(api.getIngestCapabilities?.())
        .then((caps: any) => {
          if (cancelled || !caps?.supported_archive_extensions?.length) return;
          setFileAccept([...caps.supported_archive_extensions, EVIDENCE_ACCEPT_EXTENSIONS].join(","));
        })
        .catch(() => {});
    } catch {}
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccess(false);
      setCreatedIncidentId(null);
      setIntakeMode(initialMode);
      setFormData({
        name: "",
        description: "",
        severity: "high",
        category: "detection",
        robotId: "",
        environment: "warehouse",
        tags: "",
        source: "",
        evidenceFiles: [],
      });
    }
  }, [isOpen, initialMode]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading && !showFormatsModal) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, isLoading, showFormatsModal, onClose]);

  const handleInputChange = (field: keyof typeof formData, value: string | File[]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (error) setError(null);
  };

  // Preset quick fill
  const handleApplyPreset = (preset: typeof QUICK_PRESETS[0]) => {
    setFormData((prev) => ({
      ...prev,
      source: preset.value,
      name: prev.name || preset.title,
      robotId: prev.robotId || preset.system,
      description: prev.description || `Universal package intake for ${preset.value} with automated dependency analysis and sandbox verification.`,
    }));
    setError(null);
  };

  // Helper when user selects a format from the SupportedFormatsModal
  const handleSelectExampleFromModal = (example: string) => {
    setIntakeMode("source");
    setFormData((prev) => {
      const cleanExample = example.trim();
      const suggestedTitle = `Intake: ${cleanExample}`;
      return {
        ...prev,
        source: cleanExample,
        name: prev.name || suggestedTitle,
        description: prev.description || `Universal source intake for ${cleanExample} with automated evidence indexing.`,
      };
    });
    setError(null);
  };

  const handleFilesSelected = (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    const validFiles = fileArray.filter(
      (f) =>
        f.type.startsWith("text/") ||
        /\.(zip|tar|tar\.gz|tgz|tar\.bz2|tbz2|tar\.xz|txz|gz|bz2|xz|json|jsonl|ndjson|csv|yaml|yml|toml|ini|log|txt|md|mcap|bag)$/i.test(f.name) ||
        ["application/zip", "application/gzip", "application/x-tar", "application/x-bzip2", "application/x-xz", "application/json", "application/octet-stream"].includes(f.type)
    );

    if (validFiles.length !== fileArray.length) {
      setError("Unsupported file format — archives (.zip, .tar.gz, ...) and evidence files (.json, .log, .mcap) are supported");
    }

    setFormData((prev) => {
      // Auto-name from first file if name is empty
      let newName = prev.name;
      if (!newName && validFiles[0]) {
        newName = validFiles[0].name.replace(/\.[^/.]+$/, "").replace(/[-_]/g, " ");
        newName = newName.charAt(0).toUpperCase() + newName.slice(1);
      }
      return {
        ...prev,
        evidenceFiles: validFiles,
        name: newName,
        description: prev.description || `Investigation evidence bundle uploaded from ${validFiles[0]?.name || "archive"}.`,
      };
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Generate intelligent defaults if user submitted without typing custom title/description
    let effectiveTitle = formData.name.trim();
    let effectiveDescription = formData.description.trim();

    if (!effectiveTitle) {
      if (intakeMode === "source" && formData.source.trim()) {
        effectiveTitle = `Source Intake: ${formData.source.trim()}`;
      } else if (intakeMode === "upload" && formData.evidenceFiles.length > 0) {
        effectiveTitle = `Uploaded Bundle: ${formData.evidenceFiles[0].name}`;
      } else {
        setError("Incident name is required");
        return;
      }
    }

    if (!effectiveDescription) {
      if (intakeMode === "source" && formData.source.trim()) {
        effectiveDescription = `Universal source intake for ${formData.source.trim()} with automated evidence extraction.`;
      } else if (intakeMode === "upload" && formData.evidenceFiles.length > 0) {
        effectiveDescription = `Evidence package uploaded with ${formData.evidenceFiles.length} file(s).`;
      } else {
        setError("Description is required");
        return;
      }
    }

    setIsLoading(true);
    setError(null);
    setLoadingMessage(null);

    try {
      let incidentId: string;

      if (intakeMode === "source" && formData.source.trim()) {
        setLoadingMessage("Submitting to intake queue...");
        const job = await api.ingestFromSource(formData.source.trim(), {
          title: effectiveTitle,
          description: effectiveDescription,
          systemName: formData.robotId || undefined,
        });

        setLoadingMessage(`Ingesting ${job.source_kind || "source package"}...`);
        const deadline = Date.now() + 10 * 60 * 1000;
        let status = job.status;
        let result: any = null;
        let jobError: string | null = null;

        while (Date.now() < deadline) {
          const polled = await api.getIngestJob(job.job_id);
          status = polled.status;
          result = polled.result ?? null;
          jobError = polled.error ?? null;

          if (status === "running") {
            setLoadingMessage("Extracting and indexing package artifacts...");
          }
          if (["completed", "failed", "dead_letter", "cancelled"].includes(status)) {
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }

        if (status !== "completed" || !result?.incident_id) {
          throw new Error(jobError || result?.error || `Source ingest failed with status "${status}"`);
        }
        incidentId = result.incident_id;
      } else {
        setLoadingMessage("Creating incident workspace...");
        const result = await api.create(false, {
          title: effectiveTitle,
          description: effectiveDescription,
          system_name: formData.robotId || undefined,
          custom_id: formData.tags || undefined,
        });
        if (!result?.incident_id) {
          throw new Error("Failed to create incident — no ID returned by server");
        }
        incidentId = result.incident_id;
      }

      // Upload files if any
      if (formData.evidenceFiles.length > 0) {
        setLoadingMessage(`Uploading ${formData.evidenceFiles.length} evidence file(s)...`);
        for (const file of formData.evidenceFiles) {
          await api.uploadFile(incidentId, file);
        }
      }

      setCreatedIncidentId(incidentId);
      setLoadingMessage(null);
      setSuccess(true);
      addActivity({
        type: "system",
        message: `Created incident ${incidentId}`,
        dismissible: true,
      });

      if (onSuccess) {
        onSuccess(incidentId);
        setTimeout(() => {
          onClose();
        }, 1200);
      } else {
        setTimeout(() => {
          router.push("/");
          window.location.reload();
        }, 1200);
      }
    } catch (err) {
      setLoadingMessage(null);
      const message = err instanceof Error ? err.message : "Failed to create incident";
      setError(message);
      addActivity({
        type: "error",
        message: "Failed to create incident",
        details: message,
        dismissible: true,
      });
    } finally {
      setIsLoading(false);
      setLoadingMessage(null);
    }
  };

  if (!isOpen || !mounted) return null;

  return createPortal(
    <>
      <div
        className={modalStyles()}
        onClick={onClose}
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-incident-title"
      >
        <div className={panelStyles()} onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <header className={headerStyles()}>
            <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-md,6px)] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Zap className="h-4.5 w-4.5 text-indigo-400" />
            </div>
            <div className="flex-1 min-w-0">
              <h2 id="create-incident-title" className="text-sm font-semibold text-zinc-100">
                Create New Incident
              </h2>
              <p className="text-xs text-zinc-400">
                Universal intake across 12 package managers, Git repos, local archives, and telemetry
              </p>
            </div>
            <button
              onClick={() => !isLoading && onClose()}
              className="inline-flex h-8 w-8 items-center justify-center rounded-[var(--radius-md,6px)] text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
              aria-label="Close modal"
              disabled={isLoading}
            >
              <X className="h-4 w-4" />
            </button>
          </header>

          {/* Form */}
          <form id="create-incident-form" onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
            <div className={contentStyles()}>
              {/* Success Notification */}
              {success && (
                <div className="p-4 rounded-[var(--radius-md,6px)] bg-emerald-950/30 border border-emerald-700/60 flex items-center gap-3 animate-fade-in text-emerald-300">
                  <CheckCircle className="h-5 w-5 text-emerald-400 flex-shrink-0" />
                  <div>
                    <p className="font-semibold text-emerald-300">
                      Incident {createdIncidentId} Created Successfully!
                    </p>
                    <p className="text-xs text-emerald-400/80">Loading investigation workspace...</p>
                  </div>
                </div>
              )}

              {/* Error Alert */}
              {error && !success && (
                <div className="p-3 rounded-[var(--radius-md,6px)] bg-rose-950/40 border border-rose-800/60 flex items-start gap-2.5 animate-fade-in text-rose-300">
                  <AlertCircle className="h-4 w-4 text-rose-400 flex-shrink-0 mt-0.5" />
                  <div className="flex-1 text-xs break-all leading-relaxed">{error}</div>
                </div>
              )}

              {!success && (
                <>
                  {/* Step 1: Intake Source Selector Tabs */}
                  <div>
                    <div className={sectionDividerStyles()}>
                      <span className="flex items-center gap-1.5 text-zinc-300">
                        <span className="h-4 w-4 flex items-center justify-center rounded bg-indigo-500/20 text-indigo-400 text-[10px] font-mono">1</span>
                        Select Ingestion Method
                      </span>
                    </div>

                    <div className="grid grid-cols-3 gap-2 mt-2">
                      <button
                        type="button"
                        onClick={() => {
                          setIntakeMode("source");
                          setError(null);
                        }}
                        className={`flex flex-col items-center justify-center p-2.5 rounded-[var(--radius-sm,4px)] border text-center transition-all ${
                          intakeMode === "source"
                            ? "border-indigo-500 bg-indigo-500/10 text-indigo-200 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                        }`}
                      >
                        <Globe className="h-4 w-4 mb-1 text-indigo-400" />
                        <span className="font-semibold text-[11px]">Remote Registry / Git</span>
                        <span className="text-[10px] text-zinc-500 hidden sm:inline">PyPI, npm, GitHub, crates...</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setIntakeMode("upload");
                          setError(null);
                        }}
                        className={`flex flex-col items-center justify-center p-2.5 rounded-[var(--radius-sm,4px)] border text-center transition-all ${
                          intakeMode === "upload"
                            ? "border-indigo-500 bg-indigo-500/10 text-indigo-200 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                        }`}
                      >
                        <Upload className="h-4 w-4 mb-1 text-emerald-400" />
                        <span className="font-semibold text-[11px]">Upload Archive</span>
                        <span className="text-[10px] text-zinc-500 hidden sm:inline">ZIP, TAR, GZ, JSON, MCAP...</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setIntakeMode("manual");
                          setError(null);
                        }}
                        className={`flex flex-col items-center justify-center p-2.5 rounded-[var(--radius-sm,4px)] border text-center transition-all ${
                          intakeMode === "manual"
                            ? "border-indigo-500 bg-indigo-500/10 text-indigo-200 shadow-xs"
                            : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:text-zinc-200 hover:border-zinc-700"
                        }`}
                      >
                        <Bot className="h-4 w-4 mb-1 text-amber-400" />
                        <span className="font-semibold text-[11px]">Manual Incident</span>
                        <span className="text-[10px] text-zinc-500 hidden sm:inline">Operational telemetry</span>
                      </button>
                    </div>
                  </div>

                  {/* Mode-specific source input */}
                  {intakeMode === "source" && (
                    <div className="space-y-2 p-3 rounded-[var(--radius-sm,4px)] bg-zinc-900/50 border border-zinc-800">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-medium text-zinc-200 flex items-center gap-1.5">
                          <Globe className="h-3.5 w-3.5 text-indigo-400" />
                          Source URL or Shorthand Spec *
                        </label>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setShowFormatsModal(true)}
                          className="h-6 text-[11px] text-indigo-400 hover:text-indigo-300 px-2"
                        >
                          <HelpCircle className="h-3 w-3 mr-1" />
                          Browse Formats
                        </Button>
                      </div>

                      <input
                        type="text"
                        value={formData.source}
                        onChange={(e) => handleInputChange("source", e.target.value)}
                        placeholder="e.g. pypi:requests@2.32.3 or github:octocat/Hello-World"
                        disabled={isLoading}
                        className="w-full h-8 px-2.5 rounded-[var(--radius-sm,4px)] border border-zinc-800 bg-zinc-950 font-mono text-xs text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />

                      {/* Quick Presets */}
                      <div>
                        <div className="text-[10.5px] text-zinc-500 mb-1 flex items-center justify-between">
                          <span>Quick Presets:</span>
                          <span className="text-[10px] text-zinc-600">Click to fill</span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {QUICK_PRESETS.map((preset, idx) => (
                            <button
                              key={idx}
                              type="button"
                              onClick={() => handleApplyPreset(preset)}
                              className="px-2 py-0.5 rounded bg-zinc-800/80 hover:bg-zinc-700/80 text-zinc-300 font-mono text-[10.5px] border border-zinc-700/50 transition-colors"
                            >
                              {preset.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {intakeMode === "upload" && (
                    <div className="space-y-2">
                      <div
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                        onClick={() => fileInputRef.current?.click()}
                        className={`p-5 rounded-[var(--radius-sm,4px)] border-2 border-dashed text-center cursor-pointer transition-all ${
                          isDragOver
                            ? "border-indigo-500 bg-indigo-500/10"
                            : "border-zinc-800 hover:border-zinc-700 bg-zinc-900/30"
                        }`}
                      >
                        <Upload className="h-6 w-6 text-indigo-400 mx-auto mb-2" />
                        <p className="text-xs font-medium text-zinc-200">
                          Drag &amp; drop evidence archive or single evidence file here
                        </p>
                        <p className="text-[11px] text-zinc-500 mt-1">
                          Supports .zip, .tar.gz, .tgz, .tar.xz, .json, .log, .mcap, .bag (up to 200MB uncompressed)
                        </p>
                        <input
                          ref={fileInputRef}
                          type="file"
                          multiple
                          accept={fileAccept}
                          onChange={(e) => e.target.files && handleFilesSelected(e.target.files)}
                          className="hidden"
                        />
                      </div>

                      {formData.evidenceFiles.length > 0 && (
                        <div className="space-y-1 mt-2">
                          <span className="text-[11px] text-zinc-400">Selected Files:</span>
                          {formData.evidenceFiles.map((file, idx) => (
                            <div
                              key={idx}
                              className="flex items-center justify-between p-2 rounded bg-zinc-900/60 border border-zinc-800 text-xs text-zinc-300"
                            >
                              <span className="font-mono truncate">{file.name}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-[10px] text-zinc-500">
                                  {(file.size / 1024).toFixed(1)} KB
                                </span>
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setFormData((prev) => ({
                                      ...prev,
                                      evidenceFiles: prev.evidenceFiles.filter((_, i) => i !== idx),
                                    }));
                                  }}
                                  className="text-zinc-500 hover:text-rose-400"
                                >
                                  <X className="h-3 w-3" />
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {intakeMode === "manual" && (
                    <div className="p-3 rounded-[var(--radius-sm,4px)] bg-zinc-900/40 border border-zinc-800 text-zinc-400 text-xs">
                      <p>
                        Creating a blank incident investigation workspace. You can attach telemetry logs and run hypothesis tests after creation.
                      </p>
                    </div>
                  )}

                  {/* Step 2: Incident Details */}
                  <div className="space-y-3 pt-2">
                    <div className={sectionDividerStyles()}>
                      <span className="flex items-center gap-1.5 text-zinc-300">
                        <span className="h-4 w-4 flex items-center justify-center rounded bg-indigo-500/20 text-indigo-400 text-[10px] font-mono">2</span>
                        Incident Details &amp; Operational Context
                      </span>
                    </div>

                    <div className={fieldStyles()}>
                      <Input
                        label="Incident Name *"
                        hint="Descriptive title (auto-suggested from package/file, or enter your own)"
                        placeholder="e.g. Navigation Planner Memory Exhaustion - AMR-042"
                        value={formData.name}
                        onChange={(e) => handleInputChange("name", e.target.value)}
                        required
                        error={error && !formData.name ? "Incident name is required" : undefined}
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className={fieldStyles()}>
                        <label className="text-xs font-medium text-zinc-300">Severity *</label>
                        <Select
                          value={formData.severity}
                          onValueChange={(v) => handleInputChange("severity", v)}
                          options={[
                            { value: "critical", label: "Critical - System outage / Safety stop" },
                            { value: "high", label: "High - Major subsystem failure" },
                            { value: "medium", label: "Medium - Degraded performance" },
                            { value: "low", label: "Low - Minor discrepancy" },
                          ]}
                          className="w-full"
                        />
                      </div>

                      <div className={fieldStyles()}>
                        <label className="text-xs font-medium text-zinc-300">Category *</label>
                        <Select
                          value={formData.category}
                          onValueChange={(v) => handleInputChange("category", v)}
                          options={[
                            { value: "detection", label: "Perception / Sensor Detection" },
                            { value: "navigation", label: "Navigation / Localization" },
                            { value: "planning", label: "Planning / Trajectory" },
                            { value: "control", label: "Control / Actuation" },
                            { value: "communication", label: "Network / ROS Transport" },
                            { value: "other", label: "Other / General" },
                          ]}
                          className="w-full"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                      <div className={fieldStyles()}>
                        <Input
                          label="System / Robot Identifier"
                          hint="e.g., 'AMR-042', 'FORGE-07', 'perception-worker'"
                          placeholder="AMR-042"
                          value={formData.robotId}
                          onChange={(e) => handleInputChange("robotId", e.target.value)}
                        />
                      </div>

                      <div className={fieldStyles()}>
                        <label className="text-xs font-medium text-zinc-300">Environment *</label>
                        <Select
                          value={formData.environment}
                          onValueChange={(v) => handleInputChange("environment", v)}
                          options={[
                            { value: "warehouse", label: "Warehouse / Logistics Floor" },
                            { value: "outdoor", label: "Outdoor / Field Deployment" },
                            { value: "lab", label: "Lab / Hardware Bench" },
                            { value: "simulation", label: "Simulation / Digital Twin" },
                            { value: "other", label: "Other Environment" },
                          ]}
                          className="w-full"
                        />
                      </div>
                    </div>

                    <div className={fieldStyles()}>
                      <Input
                        label="Description *"
                        hint="Brief synopsis of observed symptoms and root cause hypothesis"
                        placeholder="Describe the incident symptoms..."
                        value={formData.description}
                        onChange={(e) => handleInputChange("description", e.target.value)}
                        required
                        error={error && !formData.description ? "Description is required" : undefined}
                        className="min-h-[70px]"
                      />
                    </div>

                    <div className={fieldStyles()}>
                      <Input
                        label="Tags"
                        hint="Comma-separated tags for filtering (e.g., 'memory-leak, oom, camera-freshness')"
                        placeholder="memory-leak, camera-freshness, v42"
                        value={formData.tags}
                        onChange={(e) => handleInputChange("tags", e.target.value)}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          </form>

          {/* Footer */}
          <footer className={footerStyles()}>
            <div className="flex items-center gap-2">
              {!success && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setFormData({
                      name: "",
                      description: "",
                      severity: "high",
                      category: "detection",
                      robotId: "",
                      environment: "warehouse",
                      tags: "",
                      source: "",
                      evidenceFiles: [],
                    });
                    setError(null);
                    if (fileInputRef.current) fileInputRef.current.value = "";
                  }}
                  disabled={isLoading}
                >
                  Clear
                </Button>
              )}
              <span className={footerHintStyles()}>
                Esc to cancel • Enter to submit
              </span>
            </div>

            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => !isLoading && onClose()}
                disabled={isLoading || success}
              >
                Cancel
              </Button>

              {!success && (
                <Button
                  type="submit"
                  form="create-incident-form"
                  variant="primary"
                  size="md"
                  disabled={isLoading}
                  className="min-w-[150px]"
                >
                  {isLoading && <Loader2 className="h-4 w-4 animate-spin mr-1.5" />}
                  {isLoading
                    ? loadingMessage || "Processing..."
                    : intakeMode === "source"
                    ? "Ingest & Create Incident"
                    : intakeMode === "upload"
                    ? "Upload & Create Incident"
                    : "Create Incident"}
                </Button>
              )}

              {success && (
                <Button
                  variant="primary"
                  size="md"
                  onClick={onClose}
                  className="min-w-[150px]"
                >
                  <CheckCircle className="h-4 w-4 mr-1.5" />
                  Continue to Workspace
                </Button>
              )}
            </div>
          </footer>
        </div>
      </div>

      {/* Formats Reference Pop-up Dialog */}
      <SupportedFormatsModal
        isOpen={showFormatsModal}
        onClose={() => setShowFormatsModal(false)}
        onSelectExample={handleSelectExampleFromModal}
      />
    </>,
    document.body
  );
}
