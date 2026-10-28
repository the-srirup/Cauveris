"use client";

import React from "react";
import { SignalTag } from "../primitives/SignalTag";
import { CheckCircle2, AlertTriangle, HelpCircle, ArrowRight } from "lucide-react";

export interface HypothesisData {
  id: string;
  rank: number;
  mechanism: string;
  title: string;
  causalClaim: string;
  confidence: number; // 0 - 1
  supportingEvidence: string[];
  contradictoryEvidence: string[];
  missingEvidence: string[];
  canSimulate: boolean;
  canRepair: boolean;
  proposedParameter?: string;
  proposedIntervention?: string;
}

export interface HypothesisPlateProps extends React.HTMLAttributes<HTMLDivElement> {
  hypothesis: HypothesisData;
  selected?: boolean;
  comparisonSelected?: boolean;
  onSelect?: () => void;
  onCompare?: () => void;
  onSimulate?: () => void;
}

export function HypothesisPlate({
  hypothesis,
  selected = false,
  comparisonSelected = false,
  onSelect,
  onCompare,
  onSimulate,
  className = "",
  ...props
}: HypothesisPlateProps) {
  const confidencePercent = Math.round(hypothesis.confidence * 100);

  const confColor =
    confidencePercent >= 75
      ? "text-emerald-800 border-emerald-200 bg-emerald-50 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
      : confidencePercent >= 50
      ? "text-blue-800 border-blue-200 bg-blue-50 dark:bg-blue-950/40 dark:text-blue-300 dark:border-blue-800"
      : "text-slate-700 border-slate-200 bg-slate-100 dark:bg-slate-800 dark:text-slate-300 dark:border-slate-700";

  return (
    <div
      className={`group relative flex flex-col rounded-[var(--radius-lg,8px)] border transition-all select-none ${
        selected
          ? "border-[var(--color-accent,#0969da)] bg-[var(--color-canvas-default,#ffffff)] ring-1 ring-[var(--color-accent,#0969da)]/20 shadow-xs"
          : comparisonSelected
          ? "border-[var(--color-accent,#0969da)]/60 bg-[var(--color-canvas-default,#ffffff)] ring-1 ring-[var(--color-accent,#0969da)]/10"
          : "border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] hover:border-[var(--color-border-emphasis,#c5ced8)] shadow-xs"
      } ${className}`}
      data-hypothesis-plate
      data-hypothesis-id={hypothesis.id}
      {...props}
    >
      {/* Top Header Rail: Mechanism + Rank + Confidence */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] px-4 py-2.5 rounded-t-[calc(var(--radius-lg,8px)-1px)]">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-mono font-bold text-[var(--color-fg-muted,#5f6b76)]">
            H-{hypothesis.rank}
          </span>
          <span className="text-xs font-semibold text-[var(--color-fg-default,#1f2933)] uppercase tracking-wide truncate">
            {hypothesis.mechanism.replace(/_/g, " ")}
          </span>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <span className={`text-xs font-semibold px-2 py-0.5 border rounded-[var(--radius-sm,4px)] tabular-nums font-mono ${confColor}`}>
            {confidencePercent}% conf
          </span>
        </div>
      </div>

      {/* Main Body: Causal Claim */}
      <div className="p-4 flex flex-col gap-3">
        <div className="text-sm font-medium text-[var(--color-fg-default,#1f2933)] leading-relaxed">
          {hypothesis.causalClaim || hypothesis.title}
        </div>

        {hypothesis.proposedIntervention && (
          <div className="text-xs bg-[var(--color-canvas-subtle,#f8f9fa)] p-2.5 rounded-[var(--radius-md,6px)] border border-[var(--color-border-default,#d9e0e7)] text-[var(--color-fg-muted,#5f6b76)] flex items-center gap-2">
            <span className="text-[var(--color-accent,#0969da)] font-semibold uppercase text-[10px] tracking-wider shrink-0">
              INTERVENE:
            </span>
            <span className="text-[var(--color-fg-default,#1f2933)] font-mono truncate">{hypothesis.proposedIntervention}</span>
          </div>
        )}

        {/* Evidence Breakdown Grid */}
        <div className="grid grid-cols-3 gap-2 pt-2.5 border-t border-[var(--color-border-default,#d9e0e7)] text-xs">
          {/* Supporting */}
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-semibold text-[var(--color-fg-muted,#5f6b76)] mb-0.5">
              Supporting
            </span>
            <span className="font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {hypothesis.supportingEvidence.length} items
            </span>
          </div>

          {/* Contradictory */}
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-semibold text-[var(--color-fg-muted,#5f6b76)] mb-0.5">
              Contradicting
            </span>
            <span className="font-semibold text-rose-700 dark:text-rose-400 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              {hypothesis.contradictoryEvidence.length} items
            </span>
          </div>

          {/* Missing */}
          <div className="flex flex-col">
            <span className="text-[10px] uppercase font-semibold text-[var(--color-fg-muted,#5f6b76)] mb-0.5">
              Missing
            </span>
            <span className="font-semibold text-slate-600 dark:text-slate-400 flex items-center gap-1">
              <HelpCircle className="w-3.5 h-3.5" />
              {hypothesis.missingEvidence.length} items
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
