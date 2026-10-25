"use client";

import type { ReactNode } from "react";

export interface StatProps {
  label: string;
  value: ReactNode;
  sub?: string;
  trend?: "up" | "down" | "flat" | "success" | "danger" | "warning" | "secondary" | "muted";
  className?: string;
}

export function Stat({
  label,
  value,
  sub,
  trend,
  className = "",
}: StatProps) {
  const trendColor =
    trend === "up" || trend === "success"
      ? "text-[var(--color-success-fg)]"
      : trend === "down" || trend === "danger"
        ? "text-[var(--color-danger-fg)]"
        : trend === "warning" || trend === "secondary"
          ? "text-[var(--color-attention-fg)]"
          : "text-[var(--color-fg-muted)]";

  return (
    <div className={`rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] p-4 sm:p-5 ${className}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-fg-muted)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-2xl font-semibold text-[var(--color-fg-default)]">
        {value}
      </div>
      {sub && <div className={`mt-1 text-xs font-medium ${trendColor}`}>{sub}</div>}
    </div>
  );
}
