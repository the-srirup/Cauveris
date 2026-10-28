"use client";

import React from "react";
import { Check, AlertTriangle, XCircle, Clock, Loader2 } from "lucide-react";

export interface StageStep {
  id: string;
  name: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "SKIPPED" | "BLOCKED" | "PARTIAL";
  timestamp?: string;
  durationMs?: number;
  warnings?: string[];
  blockedReason?: string;
}

export interface StageRailProps extends React.HTMLAttributes<HTMLDivElement> {
  stages: StageStep[];
  currentStageId?: string | null;
  onSelectStage?: (stageId: string) => void;
  orientation?: "horizontal" | "vertical";
}

export function StageRail({
  stages,
  currentStageId,
  onSelectStage,
  orientation = "horizontal",
  className = "",
  ...props
}: StageRailProps) {
  const isHorizontal = orientation === "horizontal";

  return (
    <div
      className={`border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-lg,8px)] select-none shadow-xs overflow-hidden ${className}`}
      data-stage-rail
      {...props}
    >
      <div
        className={
          isHorizontal
            ? "flex flex-row items-stretch divide-x divide-[var(--color-border-default,#d9e0e7)] overflow-x-auto scrollbar-thin"
            : "flex flex-col divide-y divide-[var(--color-border-default,#d9e0e7)]"
        }
      >
        {stages.map((stage, idx) => {
          const isCurrent = stage.id === currentStageId || stage.status === "RUNNING";
          const isComplete = stage.status === "COMPLETED";
          const isFailed = stage.status === "FAILED";
          const isBlocked = stage.status === "BLOCKED";
          const isPartial = stage.status === "PARTIAL";

          const statusStyle = isComplete
            ? "bg-emerald-50/30 text-emerald-950 dark:bg-emerald-950/20 dark:text-emerald-100"
            : isFailed
            ? "bg-rose-50/40 text-rose-950 dark:bg-rose-950/20 dark:text-rose-100"
            : isBlocked
            ? "bg-slate-50/50 text-slate-700 dark:bg-slate-900/40 dark:text-slate-300"
            : isPartial
            ? "bg-amber-50/40 text-amber-950 dark:bg-amber-950/20 dark:text-amber-100"
            : isCurrent
            ? "bg-blue-50/50 text-blue-950 dark:bg-blue-950/30 dark:text-blue-100 ring-1 ring-inset ring-[var(--color-accent,#0969da)]"
            : "bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-muted,#5f6b76)]";

          return (
            <div
              key={stage.id}
              className={`group ${
                isHorizontal ? "flex-1 min-w-[170px]" : "w-full"
              } p-3.5 flex flex-col justify-between transition-colors overflow-hidden ${statusStyle} ${
                onSelectStage ? "cursor-pointer hover:opacity-90" : ""
              }`}
              onClick={() => onSelectStage?.(stage.id)}
              role={onSelectStage ? "button" : undefined}
              tabIndex={onSelectStage ? 0 : undefined}
            >
              {/* Top row: Stage index badge + Status Icon */}
              <div className="flex items-center justify-between gap-2 min-w-0 mb-2">
                <span className="font-mono text-[11px] font-semibold text-[var(--color-fg-muted,#5f6b76)] uppercase tracking-wide truncate">
                  Stage {idx + 1 < 10 ? `0${idx + 1}` : idx + 1}
                </span>
                <span className="shrink-0 flex items-center justify-center">
                  {isComplete && (
                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/15 text-emerald-600 dark:text-emerald-400">
                      <Check className="w-3 h-3 stroke-[2.5]" />
                    </span>
                  )}
                  {isFailed && (
                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-rose-500/15 text-rose-600 dark:text-rose-400">
                      <XCircle className="w-3.5 h-3.5 stroke-[2.5]" />
                    </span>
                  )}
                  {isBlocked && (
                    <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-500/15 text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="w-3.5 h-3.5 stroke-[2.5]" />
                    </span>
                  )}
                  {isCurrent && (
                    <span className="inline-flex items-center justify-center w-4 h-4">
                      <Loader2 className="w-3.5 h-3.5 text-[var(--color-accent,#0969da)] animate-spin" />
                    </span>
                  )}
                  {!isComplete && !isFailed && !isBlocked && !isCurrent && (
                    <span className="inline-flex items-center justify-center w-4 h-4 text-[var(--color-fg-subtle,#7b8794)]">
                      <Clock className="w-3.5 h-3.5" />
                    </span>
                  )}
                </span>
              </div>

              {/* Stage Name with clean multi-line wrapping and full tooltip */}
              <div
                className="text-xs font-semibold leading-snug text-[var(--color-fg-default,#1f2933)] line-clamp-2 min-h-[2.5rem] break-words font-sans min-w-0"
                title={`${idx + 1}. ${stage.name} (${stage.id})`}
              >
                {stage.name}
              </div>

              {/* Bottom info: Duration or Status */}
              <div className="mt-2.5 pt-2 border-t border-[var(--color-border-default,#d9e0e7)]/50 flex items-center justify-between gap-1 text-[11px] font-mono min-w-0">
                <span className="text-[var(--color-fg-muted,#5f6b76)] truncate">
                  {stage.durationMs !== undefined ? (
                    `${(stage.durationMs / 1000).toFixed(2)}s`
                  ) : stage.status === "RUNNING" ? (
                    <span className="text-[var(--color-accent,#0969da)] font-sans font-medium">Running…</span>
                  ) : (
                    <span className="capitalize font-sans text-[11px]">{stage.status.toLowerCase()}</span>
                  )}
                </span>

                {stage.blockedReason && (
                  <span
                    className="text-rose-600 dark:text-rose-400 text-[10px] truncate max-w-[80px]"
                    title={stage.blockedReason}
                  >
                    {stage.blockedReason}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
