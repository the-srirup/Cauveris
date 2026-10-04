"use client";

import { useState, useEffect, useRef } from "react";
import { tv } from "tailwind-variants";
import { X, Zap, Loader2, AlertCircle, CheckCircle } from "lucide-react";
import { api } from "@/lib/api";
import { Button, Input, Select, Badge } from "./ui";
import { useShell } from "@/lib/useShell";
import { useRouter } from "next/navigation";

const modalStyles = tv({
  base: `
    fixed inset-0 z-50 flex items-center justify-center
    bg-[var(--color-overlay)] backdrop-blur-sm
    animate-fade-in
  `,
});

const panelStyles = tv({
  base: `
    w-full max-w-2xl rounded-2xl border border-[var(--color-border)]
    bg-[var(--theme-background)]/95 backdrop-blur-xl shadow-2xl
    overflow-hidden flex flex-col max-h-[90vh]
    animate-scale-in
  `,
});

const headerStyles = tv({
  base: `
    flex items-center gap-3 px-6 py-4 border-b border-[var(--color-border)]
    bg-[var(--color-surface)]/60 backdrop-blur-sm
  `,
});

const contentStyles = tv({
  base: `
    px-6 py-6 space-y-5 overflow-y-auto flex-1 min-h-0
  `,
});

const footerStyles = tv({
  base: `
    flex items-center justify-between gap-3 px-6 py-4 border-t border-[var(--color-border)]
    bg-[var(--color-surface)]/60 backdrop-blur-sm flex-shrink-0
  `,
});

const footerHintStyles = tv({
  base: `
    text-[11px] text-[var(--color-text-muted)]/70 self-center
  `,
});

const fieldStyles = tv({
  base: `
    space-y-1.5
  `,
});

const helperTextStyles = tv({
  base: `
    text-xs text-[var(--color-text-muted)]
  `,
});

const errorTextStyles = tv({
  base: `
    text-xs text-brand-danger flex items-center gap-1.5
  `,
});

const sectionDividerStyles = tv({
  base: `
    flex items-center gap-3 text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]
    py-2
  `,
});

export function CreateIncidentModal({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const { addActivity } = useShell();
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    severity: "high" as "critical" | "high" | "medium" | "low",
    category: "detection" as "detection" | "navigation" | "planning" | "control" | "communication" | "other",
    robotId: "",
    environment: "warehouse" as "warehouse" | "outdoor" | "lab" | "simulation" | "other",
    tags: "",
    evidenceFiles: [] as File[],
  });
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Focus first input when modal opens
  useEffect(() => {
    if (isOpen) {
      setError(null);
      setSuccess(false);
      setFormData({
        name: "",
        description: "",
        severity: "high",
        category: "detection",
        robotId: "",
        environment: "warehouse",
        tags: "",
        evidenceFiles: [],
      });
      // Focus will be handled by autoFocus on the name input
    }
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, isLoading, onClose]);

  const handleInputChange = (field: keyof typeof formData, value: string | File[]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (error) setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setError("Incident name is required");
      return;
    }
    if (!formData.description.trim()) {
      setError("Description is required");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Create incident via API
      const result = await api.create(false, {
        title: formData.name,
        description: formData.description,
        system_name: formData.robotId || undefined,
        custom_id: formData.tags || undefined,
      });

      if (result?.incident_id) {
        setSuccess(true);
        addActivity({
          type: "system",
          message: `Created incident ${result.incident_id}`,
          dismissible: true,
        });

        // Navigate to dashboard with new incident after brief delay
        setTimeout(() => {
          router.push("/");
          window.location.reload(); // Reload to pick up new incident context
        }, 1000);
      } else {
        throw new Error("Failed to create incident - no ID returned");
      }
    } catch (err) {
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
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      const validFiles = Array.from(files).filter(f =>
        f.type === "application/zip" ||
        f.type === "application/json" ||
        f.name.endsWith(".tar.gz")
      );
      if (validFiles.length !== files.length) {
        setError("Only .zip, .json, and .tar.gz files are supported");
      }
      handleInputChange("evidenceFiles", validFiles);
    }
  };

  if (!isOpen) return null;

  return (
    <div className={modalStyles()} onClick={onClose} role="dialog" aria-modal="true" aria-labelledby="create-incident-title">
      <div className={panelStyles()} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <header className={headerStyles()}>
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
            <Zap className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <h2 id="create-incident-title" className="font-semibold text-[var(--color-text-primary)]">Create New Incident</h2>
            <p className="text-[11px] text-[var(--color-text-muted)]">Define the incident details to begin investigation</p>
          </div>
          <button
            onClick={() => !isLoading && onClose()}
            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)] transition-colors border border-transparent hover:border-[var(--color-border)]"
            aria-label="Close modal"
            disabled={isLoading}
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        {/* Form */}
        <form id="create-incident-form" onSubmit={handleSubmit}>
          <div className={contentStyles()}>
            {success && (
              <div className="p-4 rounded-xl bg-[var(--color-brand-success)]/10 border border-success/30 flex items-center gap-3 animate-fade-in">
                <CheckCircle className="h-5 w-5 text-[var(--color-brand-success)] flex-shrink-0" />
                <div>
                  <p className="font-medium text-[var(--color-brand-success)]">Incident Created Successfully!</p>
                  <p className="text-xs text-[var(--color-brand-success)]/80">Redirecting to dashboard...</p>
                </div>
              </div>
            )}

            {error && !success && (
              <div className="p-3 rounded-lg bg-[var(--color-brand-danger)]/10 border border-danger/30 flex items-center gap-2 animate-fade-in">
                <AlertCircle className="h-4 w-4 text-[var(--color-brand-danger)] flex-shrink-0" />
                <span className="text-sm text-[var(--color-brand-danger)]">{error}</span>
              </div>
            )}

            {!success && (
              <>
                {/* Required Fields Section */}
                <div className={sectionDividerStyles()}>
                  <span className="flex items-center gap-1.5">
                    <span className="h-5 w-5 flex items-center justify-center rounded bg-primary/20 text-primary text-[10px] font-mono">1</span>
                    Required Information
                  </span>
                </div>

                <div className={fieldStyles()}>
                  <Input
                    label="Incident Name *"
                    hint="Brief, descriptive name (e.g., 'Emergency Stop at Aisle B - v42 Deployment')"
                    placeholder="Enter incident name"
                    value={formData.name}
                    onChange={(e) => handleInputChange("name", e.target.value)}
                    autoFocus
                    required
                    error={error && !formData.name ? "Incident name is required" : undefined}
                  />
                </div>

                <div className={fieldStyles()}>
                  <Input
                    label="Description *"
                    hint="Detailed description of what happened, observed symptoms, and impact"
                    placeholder="Describe the incident in detail..."
                    value={formData.description}
                    onChange={(e) => handleInputChange("description", e.target.value)}
                    required
                    error={error && !formData.description ? "Description is required" : undefined}
                    className="min-h-[80px]"
                  />
                </div>

                {/* Classification Section */}
                <div className={sectionDividerStyles()}>
                  <span className="flex items-center gap-1.5">
                    <span className="h-5 w-5 flex items-center justify-center rounded bg-primary/20 text-primary text-[10px] font-mono">2</span>
                    Classification
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className={fieldStyles()}>
                    <label className="text-xs font-medium text-[var(--color-text-muted)]">Severity *</label>
                    <Select
                      value={formData.severity}
                      onValueChange={(v) => handleInputChange("severity", v)}
                      options={[
                        { value: "critical", label: "Critical - System-wide impact" },
                        { value: "high", label: "High - Major function impaired" },
                        { value: "medium", label: "Medium - Degraded performance" },
                        { value: "low", label: "Low - Minor issue" },
                      ]}
                      className="w-full"
                    />
                  </div>

                  <div className={fieldStyles()}>
                    <label className="text-xs font-medium text-[var(--color-text-muted)]">Category *</label>
                    <Select
                      value={formData.category}
                      onValueChange={(v) => handleInputChange("category", v)}
                      options={[
                        { value: "detection", label: "Perception/Detection" },
                        { value: "navigation", label: "Navigation/Localization" },
                        { value: "planning", label: "Planning/Decision Making" },
                        { value: "control", label: "Control/Actuation" },
                        { value: "communication", label: "Communication/Network" },
                        { value: "other", label: "Other" },
                      ]}
                      className="w-full"
                    />
                  </div>
                </div>

                {/* Context Section */}
                <div className={sectionDividerStyles()}>
                  <span className="flex items-center gap-1.5">
                    <span className="h-5 w-5 flex items-center justify-center rounded bg-primary/20 text-primary text-[10px] font-mono">3</span>
                    Operational Context
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className={fieldStyles()}>
                    <Input
                      label="Robot ID"
                      hint="Optional: Specific robot identifier (e.g., 'AMR-042', 'FORGE-07')"
                      placeholder="AMR-042"
                      value={formData.robotId}
                      onChange={(e) => handleInputChange("robotId", e.target.value)}
                    />
                  </div>

                  <div className={fieldStyles()}>
                    <label className="text-xs font-medium text-[var(--color-text-muted)]">Environment *</label>
                    <Select
                      value={formData.environment}
                      onValueChange={(v) => handleInputChange("environment", v)}
                      options={[
                        { value: "warehouse", label: "Warehouse/Indoor" },
                        { value: "outdoor", label: "Outdoor/Field" },
                        { value: "lab", label: "Lab/Test Facility" },
                        { value: "simulation", label: "Simulation/Digital Twin" },
                        { value: "other", label: "Other" },
                      ]}
                      className="w-full"
                    />
                  </div>
                </div>

                <div className={fieldStyles()}>
                  <Input
                    label="Tags"
                    hint="Comma-separated tags for filtering (e.g., 'emergency-stop, latency, freshness-budget, v42')"
                    placeholder="emergency-stop, latency, v42"
                    value={formData.tags}
                    onChange={(e) => handleInputChange("tags", e.target.value)}
                  />
                </div>

                {/* Evidence Section */}
                <div className={sectionDividerStyles()}>
                  <span className="flex items-center gap-1.5">
                    <span className="h-5 w-5 flex items-center justify-center rounded bg-primary/20 text-primary text-[10px] font-mono">4</span>
                    Evidence Files (Optional)
                  </span>
                </div>

                <div className={fieldStyles()}>
                  <div className="relative">
                    <div
                      className={`border-2 border-dashed rounded-xl p-6 text-center transition-all ${
                        formData.evidenceFiles.length > 0
                          ? "border-[var(--color-brand-success)]/50 bg-[var(--color-brand-success)]/5"
                          : "border-[var(--color-border)] hover:border-[var(--color-brand-primary)]/30 hover:bg-[var(--color-surface)]"
                      }`}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".zip,.json,.tar.gz"
                        multiple
                        onChange={handleFileChange}
                        className="absolute inset-0 opacity-0 cursor-pointer"
                        disabled={isLoading}
                      />
                      {formData.evidenceFiles.length > 0 ? (
                        <>
                          <div className="flex items-center justify-center gap-2 mb-2">
                            <span className="text-sm font-medium text-[var(--color-brand-success)]">
                              {formData.evidenceFiles.length} file(s) selected
                            </span>
                            <Badge tone="success" className="text-xs">
                              Ready
                            </Badge>
                          </div>
                          <ul className="text-xs text-[var(--color-text-muted)] space-y-1 text-left max-h-24 overflow-y-auto">
                            {formData.evidenceFiles.map((f, i) => (
                              <li key={i} className="flex items-center gap-2">
                                <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-brand-success)]" />
                                {f.name} ({(f.size / 1024).toFixed(1)} KB)
                              </li>
                            ))}
                          </ul>
                        </>
                      ) : (
                        <>
                          <div className="text-[var(--color-text-muted)] mb-2">Click or drag to upload evidence files</div>
                          <div className="text-[11px] text-[var(--color-text-muted)]/70">Supported: .zip, .json, .tar.gz</div>
                        </>
                      )}
                    </div>
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
                    evidenceFiles: [],
                  });
                  setError(null);
                  fileInputRef.current && (fileInputRef.current.value = "");
                }}
                disabled={isLoading}
              >
                Clear Form
              </Button>
            )}
            <span className={footerHintStyles()}>
              Esc to close • Enter to submit
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
                className="min-w-[140px]"
              >
                {isLoading && <Loader2 className="h-4 w-4 animate-spin" />}
                {isLoading ? "Creating..." : "Create Incident"}
              </Button>
            )}
            {success && (
              <Button
                variant="primary"
                size="md"
                onClick={onClose}
                className="min-w-[140px]"
              >
                <CheckCircle className="h-4 w-4" />
                Continue to Dashboard
              </Button>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}