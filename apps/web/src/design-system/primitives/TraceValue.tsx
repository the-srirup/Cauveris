"use client";

import React from "react";
import { SignalTag, SignalProvenance } from "./SignalTag";

export interface TraceValueProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  value: string | number | React.ReactNode;
  unit?: string;
  provenance?: SignalProvenance | string;
  uncertainty?: string | number;
  source?: string;
  delta?: {
    value: string | number;
    direction: "positive" | "negative" | "neutral";
  };
  onSelect?: () => void;
  selected?: boolean;
}

export function TraceValue({
  label,
  value,
  unit,
  provenance = "OBSERVED",
  uncertainty,
  source,
  delta,
  onSelect,
  selected = false,
  className = "",
  ...props
}: TraceValueProps) {
  return (
    <div
      className={`group relative flex flex-col justify-between p-3.5 rounded-[var(--radius-lg,8px)] border transition-colors select-none ${
        selected
          ? "border-[var(--color-accent,#0969da)] bg-[var(--color-canvas-default,#ffffff)] ring-1 ring-[var(--color-accent,#0969da)]/20 shadow-xs"
          : "border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] hover:border-[var(--color-border-emphasis,#c5ced8)] shadow-xs"
      } ${onSelect ? "cursor-pointer" : ""} ${className}`}
      onClick={onSelect}
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={(e) => {
        if (onSelect && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect();
        }
      }}
      data-trace-value
      {...props}
    >
      {/* Top Header: Label + Provenance */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="font-sans text-xs font-medium text-[var(--color-fg-muted,#5f6b76)] truncate">
          {label}
        </span>
        {provenance && (
          <SignalTag signal={provenance} size="xs" />
        )}
      </div>

      {/* Primary Value & Unit */}
      <div className="flex items-baseline gap-1.5 my-1">
        <span className="font-sans text-xl font-bold tracking-tight tabular-nums text-[var(--color-fg-default,#1f2933)]">
          {value !== undefined && value !== null ? String(value) : "—"}
        </span>
        {unit && (
          <span className="font-sans text-xs text-[var(--color-fg-muted,#5f6b76)]">
            {unit}
          </span>
        )}
        {uncertainty !== undefined && (
          <span className="font-mono text-[11px] text-[var(--color-fg-subtle,#7b8794)]" title="Uncertainty margin">
            ±{uncertainty}
          </span>
        )}
      </div>

      {/* Comparison Delta or Source metadata */}
      <div className="flex items-center justify-between text-xs text-[var(--color-fg-muted,#5f6b76)] mt-2 pt-2 border-t border-[var(--color-border-default,#d9e0e7)]">
        {delta ? (
          <span
            className={`font-medium tabular-nums ${
              delta.direction === "positive"
                ? "text-[var(--color-success-fg,#1a7f37)]"
                : delta.direction === "negative"
                ? "text-[var(--color-danger-fg,#cf222e)]"
                : "text-[var(--color-fg-muted,#5f6b76)]"
            }`}
          >
            {delta.direction === "positive" ? "▲ +" : delta.direction === "negative" ? "▼ " : "● "}
            {delta.value}
          </span>
        ) : (
          <span className="truncate text-[11px]" title={source || "Raw telemetry"}>
            {source ? `src: ${source}` : "direct signal"}
          </span>
        )}
        {onSelect && (
          <span className="text-[10px] text-[var(--color-accent,#0969da)] opacity-0 group-hover:opacity-100 transition-opacity font-medium">
            Inspect →
          </span>
        )}
      </div>
    </div>
  );
}
