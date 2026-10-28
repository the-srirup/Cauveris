"use client";

import React from "react";
import { Check, X, AlertTriangle, Clock } from "lucide-react";

export interface VerificationCheckRecord {
  id: string;
  name: string;
  category: "structural" | "model" | "tests" | "runtime" | "staging" | "security";
  observedValue: string | number;
  operator: "<" | "<=" | ">" | ">=" | "==" | "!=" | "IN_RANGE" | "CONTAINS" | "MATCHES";
  threshold: string | number;
  result: "PASS" | "FAIL" | "WARNING" | "SKIPPED" | "UNAVAILABLE";
  sourceArtifact?: string;
  executedAt?: string;
  durationMs?: number;
  provenance?: string;
}

export interface VerificationLedgerProps extends React.HTMLAttributes<HTMLDivElement> {
  checks: VerificationCheckRecord[];
  achievedLevel?: string;
  onSelectCheck?: (check: VerificationCheckRecord) => void;
  selectedCheckId?: string;
}

export function VerificationLedger({
  checks,
  achievedLevel = "RUNTIME_VERIFIED",
  onSelectCheck,
  selectedCheckId,
  className = "",
  ...props
}: VerificationLedgerProps) {
  const groupedChecks = checks.reduce((acc, c) => {
    if (!acc[c.category]) acc[c.category] = [];
    acc[c.category].push(c);
    return acc;
  }, {} as Record<string, VerificationCheckRecord[]>);

  const categories = Object.keys(groupedChecks);

  return (
    <div
      className={`flex flex-col border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-lg,8px)] text-xs select-none shadow-xs ${className}`}
      data-verification-ledger
      {...props}
    >
      {/* Top Banner: Prominent Achieved Level */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] px-4 py-3 rounded-t-[calc(var(--radius-lg,8px)-1px)]">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted,#5f6b76)]">
            Certified Verification Level:
          </span>
          <span className="px-2.5 py-1 text-xs font-bold border border-emerald-200 bg-emerald-50 text-emerald-800 rounded-[var(--radius-sm,4px)] font-mono dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800">
            {achievedLevel}
          </span>
        </div>
        <div className="text-xs font-medium text-[var(--color-fg-muted,#5f6b76)]">
          {checks.filter((c) => c.result === "PASS").length} of {checks.length} assertions passed
        </div>
      </div>

      {/* Ledger Table Header */}
      <div className="grid grid-cols-12 gap-2 px-4 py-2.5 border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] text-xs font-semibold text-[var(--color-fg-muted,#5f6b76)] uppercase">
        <div className="col-span-4">Assertion & Gate</div>
        <div className="col-span-2 text-right">Observed</div>
        <div className="col-span-1 text-center font-mono">Op</div>
        <div className="col-span-2">Threshold</div>
        <div className="col-span-1 text-center">Result</div>
        <div className="col-span-2 text-right">Source</div>
      </div>

      {/* Ledger Rows grouped by Category */}
      <div className="divide-y divide-[var(--color-border-default,#d9e0e7)] overflow-y-auto max-h-[600px] rounded-b-[calc(var(--radius-lg,8px)-1px)]">
        {categories.map((category) => (
          <div key={category} className="flex flex-col">
            {/* Category Subheader */}
            <div className="px-4 py-2 bg-[var(--color-canvas-subtle,#f8f9fa)]/60 text-xs font-bold uppercase tracking-wider text-[var(--color-fg-muted,#5f6b76)] border-b border-[var(--color-border-default,#d9e0e7)] flex items-center justify-between">
              <span>{category.toUpperCase()} Assertions</span>
              <span className="text-[11px] font-normal text-[var(--color-fg-muted,#5f6b76)]">
                {groupedChecks[category].length} checks
              </span>
            </div>

            {/* Category Checks */}
            {groupedChecks[category].map((check) => {
              const isSelected = check.id === selectedCheckId;
              const isPass = check.result === "PASS";
              const isFail = check.result === "FAIL";
              const isWarn = check.result === "WARNING";

              return (
                <div
                  key={check.id}
                  onClick={() => onSelectCheck?.(check)}
                  role={onSelectCheck ? "button" : undefined}
                  tabIndex={onSelectCheck ? 0 : undefined}
                  className={`grid grid-cols-12 gap-2 px-4 py-2.5 items-center transition-colors border-b border-[var(--color-border-default,#d9e0e7)]/50 ${
                    isSelected
                      ? "bg-blue-50/70 text-[var(--color-accent,#0969da)] border-l-2 border-l-[var(--color-accent,#0969da)] pl-3.5 dark:bg-blue-950/30"
                      : isFail
                      ? "bg-rose-50/30 hover:bg-rose-50/50 text-[var(--color-fg-default,#1f2933)] dark:bg-rose-950/10"
                      : "hover:bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-default,#1f2933)]"
                  } ${onSelectCheck ? "cursor-pointer" : ""}`}
                >
                  {/* Name */}
                  <div className="col-span-4 flex items-center gap-2 truncate">
                    <span className="shrink-0">
                      {isPass && <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />}
                      {isFail && <X className="w-4 h-4 text-rose-600 dark:text-rose-400" />}
                      {isWarn && <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400" />}
                      {!isPass && !isFail && !isWarn && (
                        <Clock className="w-4 h-4 text-slate-400" />
                      )}
                    </span>
                    <span className="font-medium text-[var(--color-fg-default,#1f2933)] truncate" title={check.name}>
                      {check.name}
                    </span>
                  </div>

                  {/* Observed Value */}
                  <div className="col-span-2 text-right tabular-nums text-[var(--color-fg-default,#1f2933)] font-mono font-semibold truncate">
                    {String(check.observedValue)}
                  </div>

                  {/* Operator */}
                  <div className="col-span-1 text-center text-[var(--color-fg-muted,#5f6b76)] font-mono">
                    {check.operator}
                  </div>

                  {/* Threshold */}
                  <div className="col-span-2 tabular-nums text-[var(--color-fg-muted,#5f6b76)] font-mono truncate">
                    {String(check.threshold)}
                  </div>

                  {/* Result Badge */}
                  <div className="col-span-1 flex justify-center">
                    <span
                      className={`px-2 py-0.5 text-[10px] font-bold rounded-[var(--radius-sm,4px)] border ${
                        isPass
                          ? "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
                          : isFail
                          ? "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
                          : isWarn
                          ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                          : "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700"
                      }`}
                    >
                      {check.result}
                    </span>
                  </div>

                  {/* Source */}
                  <div className="col-span-2 text-right truncate text-[11px] text-[var(--color-fg-muted,#5f6b76)] font-mono" title={check.sourceArtifact || "Replay"}>
                    {check.sourceArtifact ? check.sourceArtifact.split("/").pop() : "replay"}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
