"use client";

import React from "react";
import { SignalTag } from "../primitives/SignalTag";
import { FileText, Database, Code } from "lucide-react";

export interface EvidenceRowData {
  id: string;
  path: string;
  type: string;
  sizeBytes: number;
  recordCount?: number;
  parser: string;
  parseStatus: "PARSED" | "PARTIAL" | "UNPARSED" | "UNKNOWN" | "ERROR";
  contributesToDiagnosis: boolean;
  isEditable?: boolean;
  warnings?: string[];
  provenance?: string;
  hashSha256?: string;
}

export interface EvidenceRowProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "onSelect"> {
  artifact: EvidenceRowData;
  selected?: boolean;
  onSelect?: (artifact: EvidenceRowData) => void;
}

export function EvidenceRow({
  artifact,
  selected = false,
  onSelect,
  className = "",
  ...props
}: EvidenceRowProps) {
  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div
      className={`group flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-[var(--color-border-default,#d9e0e7)] text-xs select-none transition-colors ${
        selected
          ? "bg-blue-50/70 text-[var(--color-accent,#0969da)] border-l-2 border-l-[var(--color-accent,#0969da)] pl-3 dark:bg-blue-950/30"
          : "bg-[var(--color-canvas-default,#ffffff)] hover:bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-default,#1f2933)]"
      } ${onSelect ? "cursor-pointer" : ""} ${className}`}
      onClick={() => onSelect?.(artifact)}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect(artifact);
        }
      }}
      data-evidence-row
      data-path={artifact.path}
      {...props}
    >
      {/* Type Icon & Relative Path */}
      <div className="flex items-center gap-2.5 min-w-0 flex-1">
        <span className="shrink-0 text-[var(--color-fg-muted,#5f6b76)]">
          {artifact.type.includes("json") || artifact.type.includes("yaml") ? (
            <Code className="w-4 h-4" />
          ) : artifact.type.includes("mcap") || artifact.type.includes("csv") ? (
            <Database className="w-4 h-4" />
          ) : (
            <FileText className="w-4 h-4" />
          )}
        </span>
        <span
          className="font-mono text-xs text-[var(--color-fg-default,#1f2933)] truncate font-medium"
          title={artifact.path}
        >
          {artifact.path}
        </span>
        {artifact.isEditable && (
          <span className="text-[10px] px-1.5 py-0.5 border border-slate-200 bg-slate-100 text-slate-700 font-medium rounded-[var(--radius-sm,4px)] shrink-0 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300">
            EDITABLE
          </span>
        )}
      </div>

      {/* Parser state, Record count, Size */}
      <div className="flex items-center gap-3.5 shrink-0 text-xs text-[var(--color-fg-muted,#5f6b76)]">
        {artifact.recordCount !== undefined && (
          <span className="tabular-nums font-mono" title="Record Count">
            {artifact.recordCount.toLocaleString()} recs
          </span>
        )}

        <span className="tabular-nums font-mono" title="File Size">
          {formatSize(artifact.sizeBytes)}
        </span>

        {artifact.provenance && (
          <SignalTag signal={artifact.provenance} size="xs" />
        )}
      </div>
    </div>
  );
}
