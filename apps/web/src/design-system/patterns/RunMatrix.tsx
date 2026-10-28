"use client";

import React from "react";
import { Check, X, AlertTriangle } from "lucide-react";

export interface MetricComparisonRow {
  metricName: string;
  unit?: string;
  baseline: string | number;
  intervention: string | number;
  alternative?: string | number;
  invariantStatus: "SATISFIED" | "VIOLATED" | "WARNING" | "UNTESTED";
  uncertainty?: string;
  provenance: string;
}

export interface RunMatrixProps extends React.HTMLAttributes<HTMLDivElement> {
  rows: MetricComparisonRow[];
  baselineLabel?: string;
  interventionLabel?: string;
  alternativeLabel?: string;
}

export function RunMatrix({
  rows,
  baselineLabel = "Observed Baseline",
  interventionLabel = "Candidate Intervention",
  alternativeLabel = "Alternative Candidate",
  className = "",
  ...props
}: RunMatrixProps) {
  return (
    <div
      className={`flex flex-col border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-lg,8px)] text-xs select-none shadow-xs ${className}`}
      data-run-matrix
      {...props}
    >
      {/* Header */}
      <div className="grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] text-xs uppercase font-semibold text-[var(--color-fg-muted,#5f6b76)] rounded-t-[calc(var(--radius-lg,8px)-1px)]">
        <div className="col-span-4">Metric & Invariant</div>
        <div className="col-span-2 text-right">{baselineLabel}</div>
        <div className="col-span-2 text-right text-[var(--color-fg-default,#1f2933)]">{interventionLabel}</div>
        <div className="col-span-2 text-right text-[var(--color-fg-muted,#5f6b76)]">{alternativeLabel}</div>
        <div className="col-span-2 text-center">Invariant Gate</div>
      </div>

      {/* Rows */}
      <div className="divide-y divide-[var(--color-border-default,#d9e0e7)] overflow-y-auto max-h-[400px] rounded-b-[calc(var(--radius-lg,8px)-1px)]">
        {rows.map((row) => {
          const isSatisfied = row.invariantStatus === "SATISFIED";
          const isViolated = row.invariantStatus === "VIOLATED";
          const isWarn = row.invariantStatus === "WARNING";

          return (
            <div
              key={row.metricName}
              className="grid grid-cols-12 gap-2 px-4 py-2.5 items-center hover:bg-[var(--color-canvas-subtle,#f8f9fa)] transition-colors"
            >
              {/* Metric & Unit */}
              <div className="col-span-4 flex flex-col">
                <span className="font-semibold text-[var(--color-fg-default,#1f2933)] truncate">
                  {row.metricName}
                </span>
                <span className="text-[11px] text-[var(--color-fg-muted,#5f6b76)]">
                  {row.unit || "scalar"} • {row.provenance}
                </span>
              </div>

              {/* Baseline */}
              <div className="col-span-2 text-right tabular-nums text-[var(--color-fg-muted,#5f6b76)] font-mono font-medium truncate">
                {String(row.baseline)}
              </div>

              {/* Intervention */}
              <div className="col-span-2 text-right tabular-nums text-[var(--color-fg-default,#1f2933)] font-mono font-semibold truncate">
                {String(row.intervention)}
              </div>

              {/* Alternative */}
              <div className="col-span-2 text-right tabular-nums text-[var(--color-fg-muted,#5f6b76)] font-mono truncate">
                {row.alternative !== undefined ? String(row.alternative) : "—"}
              </div>

              {/* Invariant status */}
              <div className="col-span-2 flex justify-center">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-[var(--radius-sm,4px)] border ${
                    isSatisfied
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
                      : isViolated
                      ? "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
                      : "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                  }`}
                >
                  {isSatisfied && <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />}
                  {isViolated && <X className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />}
                  {isWarn && <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />}
                  {row.invariantStatus}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
