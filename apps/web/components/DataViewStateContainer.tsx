import React, { ReactNode } from "react";
import { Loader2, AlertTriangle, AlertCircle, HelpCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/Button";

export type ViewStateKind =
  | "EMPTY"
  | "LOADING"
  | "SUCCESS"
  | "PARTIAL"
  | "UNSUPPORTED"
  | "ERROR"
  | "STALE"
  | "CANCELLED";

interface DataViewStateProps {
  state: ViewStateKind;
  children: ReactNode;
  loadingMessage?: string;
  errorMessage?: string;
  emptyTitle?: string;
  emptyMessage?: string;
  emptyAction?: { label: string; onClick: () => void };
  onRetry?: () => void;
  unsupportedMessage?: string;
  limitations?: string[];
  manualSuggestions?: string[];
  className?: string;
}

export function DataViewStateContainer({
  state,
  children,
  loadingMessage = "Loading real data from backend...",
  errorMessage = "Failed to load state from backend",
  emptyTitle = "No Data Available",
  emptyMessage = "There are no records found for this incident view.",
  emptyAction,
  onRetry,
  unsupportedMessage = "This incident artifact or mechanism is outside declared capabilities.",
  limitations = [],
  manualSuggestions = [],
  className = "",
}: DataViewStateProps) {
  if (state === "LOADING") {
    return (
      <div className={`flex flex-col items-center justify-center py-16 px-4 text-center ${className}`}>
        <Loader2 className="h-8 w-8 animate-spin text-[var(--color-accent-fg)] mb-3" />
        <p className="text-sm font-medium text-[var(--color-fg-default)]">{loadingMessage}</p>
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">Connecting to Cauveris API contracts</p>
      </div>
    );
  }

  if (state === "ERROR") {
    return (
      <div className={`p-6 rounded-[var(--radius-md)] bg-[var(--color-danger-muted)] border border-[var(--color-danger-subtle)] my-4 ${className}`}>
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-[var(--color-danger-fg)] shrink-0 mt-0.5" />
          <div className="flex-1 space-y-1">
            <h4 className="text-sm font-bold text-[var(--color-danger-fg)]">Operation Failed</h4>
            <p className="text-xs text-[var(--color-fg-default)]">{errorMessage}</p>
          </div>
          {onRetry && (
            <Button variant="danger" size="sm" onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      </div>
    );
  }

  if (state === "EMPTY") {
    return (
      <div className={`text-center py-12 px-4 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)]/40 my-4 ${className}`}>
        <FileText className="h-8 w-8 text-[var(--color-fg-muted)] mx-auto mb-2" />
        <h4 className="text-sm font-semibold text-[var(--color-fg-default)]">{emptyTitle}</h4>
        <p className="text-xs text-[var(--color-fg-muted)] mt-1 max-w-sm mx-auto">{emptyMessage}</p>
        {emptyAction && (
          <div className="mt-4">
            <Button variant="outline" size="sm" onClick={emptyAction.onClick}>
              {emptyAction.label}
            </Button>
          </div>
        )}
      </div>
    );
  }

  if (state === "UNSUPPORTED") {
    return (
      <div className={`p-6 rounded-[var(--radius-md)] bg-[var(--color-attention-muted)] border border-[var(--color-attention-subtle)] my-4 ${className}`}>
        <div className="flex items-start gap-3">
          <HelpCircle className="h-5 w-5 text-[var(--color-attention-fg)] shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2">
            <h4 className="text-sm font-bold text-[var(--color-attention-fg)]">Unsupported Mechanism Boundary</h4>
            <p className="text-xs text-[var(--color-fg-default)]">{unsupportedMessage}</p>
            {limitations.length > 0 && (
              <div className="text-xs space-y-1 text-[var(--color-fg-muted)]">
                <span className="font-semibold text-[var(--color-fg-default)]">Identified Limitations:</span>
                <ul className="list-disc list-inside">
                  {limitations.map((lim, i) => (
                    <li key={i}>{lim}</li>
                  ))}
                </ul>
              </div>
            )}
            {manualSuggestions.length > 0 && (
              <div className="text-xs space-y-1 text-[var(--color-fg-muted)] pt-1">
                <span className="font-semibold text-[var(--color-fg-default)]">Recommended Manual Actions:</span>
                <ul className="list-disc list-inside">
                  {manualSuggestions.map((sug, i) => (
                    <li key={i}>{sug}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (state === "CANCELLED") {
    return (
      <div className={`p-4 rounded-[var(--radius-md)] bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] my-4 text-center ${className}`}>
        <AlertTriangle className="h-5 w-5 text-[var(--color-attention-fg)] mx-auto mb-1" />
        <h4 className="text-sm font-semibold text-[var(--color-fg-default)]">Investigation Cancelled</h4>
        <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">The pipeline run was stopped before this stage could conclude.</p>
      </div>
    );
  }

  return <>{children}</>;
}
