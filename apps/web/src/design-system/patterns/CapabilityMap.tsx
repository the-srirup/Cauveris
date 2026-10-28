"use client";

import React from "react";
import { Check, X, AlertTriangle } from "lucide-react";

export interface CapabilityItem {
  key: "ingestion" | "extraction" | "diagnosis" | "simulation" | "repair" | "editing" | "verification" | "export";
  name: string;
  capable: boolean;
  blockedReason?: string;
  confidence?: number;
}

export interface CapabilityMapProps extends React.HTMLAttributes<HTMLDivElement> {
  capabilities: CapabilityItem[];
  decision?: "PROCEED" | "REFUSE" | "PARTIAL";
  decisionReason?: string;
  onSelectCapability?: (cap: CapabilityItem) => void;
}

export function CapabilityMap({
  capabilities,
  decision = "PROCEED",
  decisionReason,
  onSelectCapability,
  className = "",
  ...props
}: CapabilityMapProps) {
  const isRefusal = decision === "REFUSE";
  const isPartial = decision === "PARTIAL";

  return (
    <div
      className={`flex flex-col border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-lg,8px)] text-xs select-none shadow-xs ${className}`}
      data-capability-map
      {...props}
    >
      {/* Header with Decision */}
      <div className="flex items-center justify-between border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] px-4 py-2.5 rounded-t-[calc(var(--radius-lg,8px)-1px)]">
        <div className="flex items-center gap-2.5">
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--color-fg-muted,#5f6b76)]">
            Capability Boundaries:
          </span>
          <span
            className={`px-2 py-0.5 text-xs font-semibold rounded-[var(--radius-sm,4px)] border ${
              isRefusal
                ? "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/40 dark:text-rose-300 dark:border-rose-800"
                : isPartial
                ? "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
                : "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
            }`}
          >
            {decision}
          </span>
        </div>
        {decisionReason && (
          <span className="text-xs text-[var(--color-fg-muted,#5f6b76)] truncate max-w-sm" title={decisionReason}>
            {decisionReason}
          </span>
        )}
      </div>

      {/* 8-Node Linear Capability Flow */}
      <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-8 divide-x divide-y md:divide-y-0 divide-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-b-[calc(var(--radius-lg,8px)-1px)]">
        {capabilities.map((cap) => {
          const isOk = cap.capable;
          return (
            <div
              key={cap.key}
              onClick={() => onSelectCapability?.(cap)}
              className={`p-3 flex flex-col justify-between transition-colors ${
                isOk
                  ? "hover:bg-[var(--color-canvas-subtle,#f8f9fa)] text-[var(--color-fg-default,#1f2933)]"
                  : "bg-rose-50/20 hover:bg-rose-50/40 text-[var(--color-fg-default,#1f2933)] dark:bg-rose-950/10"
              } ${onSelectCapability ? "cursor-pointer" : ""}`}
            >
              <div className="flex items-center justify-between text-[11px] text-[var(--color-fg-muted,#5f6b76)] uppercase mb-1 font-medium">
                <span>{cap.name}</span>
                {isOk ? (
                  <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <X className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />
                )}
              </div>
              <div
                className={`text-xs font-semibold truncate ${
                  isOk ? "text-[var(--color-fg-default,#1f2933)]" : "text-rose-600 dark:text-rose-400"
                }`}
              >
                {isOk ? "Capable" : "Blocked"}
              </div>
              {cap.blockedReason && (
                <div
                  className="text-[10px] text-rose-600/80 dark:text-rose-400/80 truncate mt-1"
                  title={cap.blockedReason}
                >
                  {cap.blockedReason}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
