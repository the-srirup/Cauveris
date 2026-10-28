import React from "react";
import { Badge } from "@/components/ui/Badge";
import { Info, HelpCircle } from "lucide-react";
import { Tooltip } from "@/components/Tooltip";

export type ProvenanceKind =
  | "OBSERVED"
  | "DECLARED"
  | "DERIVED"
  | "CALIBRATED"
  | "INFERRED"
  | "SIMULATED"
  | "UNAVAILABLE";

export interface ProvenanceDetails {
  value: string | number | null | undefined;
  unit?: string;
  evidenceType?: string;
  sourceFile?: string;
  sourceLocator?: string;
  formulaOrModel?: string;
  assumptions?: string[];
  confidence?: number;
  uncertainty?: number | string;
  timestamp?: string;
  kind?: ProvenanceKind;
}

interface ProvenanceBadgeProps {
  kind: ProvenanceKind;
  size?: "sm" | "md";
  className?: string;
}

export function ProvenanceBadge({ kind, size = "sm", className }: ProvenanceBadgeProps) {
  const variantMap: Record<ProvenanceKind, "success" | "warning" | "primary" | "muted" | "danger"> = {
    OBSERVED: "success",
    DECLARED: "primary",
    DERIVED: "primary",
    CALIBRATED: "success",
    INFERRED: "warning",
    SIMULATED: "warning",
    UNAVAILABLE: "muted",
  };

  return (
    <Badge variant={variantMap[kind] || "muted"} size={size} className={className}>
      {kind}
    </Badge>
  );
}

interface ProvenanceMetricProps {
  label: string;
  provenance: ProvenanceDetails;
  className?: string;
}

export function ProvenanceMetric({ label, provenance, className = "" }: ProvenanceMetricProps) {
  const kind: ProvenanceKind = provenance.kind || (provenance.value === null || provenance.value === undefined ? "UNAVAILABLE" : "OBSERVED");

  const tooltipContent = (
    <div className="text-left space-y-1.5 p-1 max-w-xs text-xs">
      <div className="font-semibold border-b border-[var(--color-border-default)] pb-1 flex items-center justify-between">
        <span>Provenance Details</span>
        <ProvenanceBadge kind={kind} size="sm" />
      </div>
      {provenance.sourceFile && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Source: </span>
          <span className="font-mono text-[var(--color-fg-default)]">{provenance.sourceFile}</span>
          {provenance.sourceLocator && <span className="font-mono">:{provenance.sourceLocator}</span>}
        </div>
      )}
      {provenance.evidenceType && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Evidence Type: </span>
          <span>{provenance.evidenceType}</span>
        </div>
      )}
      {provenance.formulaOrModel && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Model: </span>
          <span className="font-mono">{provenance.formulaOrModel}</span>
        </div>
      )}
      {provenance.confidence !== undefined && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Confidence: </span>
          <span className="font-mono">{(provenance.confidence * 100).toFixed(0)}%</span>
        </div>
      )}
      {provenance.uncertainty !== undefined && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Uncertainty: </span>
          <span className="font-mono">±{provenance.uncertainty}</span>
        </div>
      )}
      {provenance.timestamp && (
        <div>
          <span className="text-[var(--color-fg-muted)]">Timestamp: </span>
          <span className="font-mono">{provenance.timestamp}</span>
        </div>
      )}
    </div>
  );

  return (
    <div className={`flex items-center justify-between py-1.5 border-b border-[var(--color-border-muted)] text-xs ${className}`}>
      <span className="text-[var(--color-fg-muted)] flex items-center gap-1">
        {label}
        <Tooltip content={tooltipContent} position="top">
          <button type="button" className="text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] inline-flex items-center" aria-label={`View provenance for ${label}`}>
            <HelpCircle className="h-3 w-3" />
          </button>
        </Tooltip>
      </span>
      <div className="flex items-center gap-2">
        <span className="font-mono font-semibold text-[var(--color-fg-default)]">
          {provenance.value !== null && provenance.value !== undefined ? String(provenance.value) : "—"}
          {provenance.unit ? ` ${provenance.unit}` : ""}
        </span>
        <ProvenanceBadge kind={kind} size="sm" />
      </div>
    </div>
  );
}
