"use client";

import React from "react";

export type SignalProvenance =
  | "OBSERVED"
  | "DECLARED"
  | "DERIVED"
  | "CALIBRATED"
  | "INFERRED"
  | "SIMULATED"
  | "VERIFIED"
  | "WARNING"
  | "FAILURE"
  | "UNAVAILABLE"
  | "SAMPLE DATA"
  | "UNKNOWN";

export interface SignalTagProps extends React.HTMLAttributes<HTMLSpanElement> {
  signal: SignalProvenance | string;
  geometry?: "left-rail" | "clipped-corner" | "underline" | "instrument-box";
  size?: "xs" | "sm" | "md";
  interactive?: boolean;
}

const SIGNAL_CONFIG: Record<
  string,
  { label: string; dotColor: string; className: string }
> = {
  OBSERVED: {
    label: "OBSERVED",
    dotColor: "#0969da",
    className: "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  },
  DECLARED: {
    label: "DECLARED",
    dotColor: "#0969da",
    className: "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  },
  DERIVED: {
    label: "DERIVED",
    dotColor: "#8250df",
    className: "bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
  },
  CALIBRATED: {
    label: "CALIBRATED",
    dotColor: "#0969da",
    className: "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
  },
  INFERRED: {
    label: "INFERRED",
    dotColor: "#8250df",
    className: "bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
  },
  SIMULATED: {
    label: "SIMULATED",
    dotColor: "#8250df",
    className: "bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
  },
  VERIFIED: {
    label: "VERIFIED",
    dotColor: "#1a7f37",
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  },
  WARNING: {
    label: "WARNING",
    dotColor: "#9a6700",
    className: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  },
  FAILURE: {
    label: "FAILURE",
    dotColor: "#cf222e",
    className: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  },
  UNAVAILABLE: {
    label: "UNAVAILABLE",
    dotColor: "#5f6b76",
    className: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
  },
  "SAMPLE DATA": {
    label: "SAMPLE DATA",
    dotColor: "#b58105",
    className: "bg-amber-50 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300 font-bold",
  },
  UNKNOWN: {
    label: "UNKNOWN",
    dotColor: "#5f6b76",
    className: "bg-slate-100 text-slate-600 dark:bg-slate-700/40 dark:text-slate-300",
  },
};

export function SignalTag({
  signal,
  geometry = "instrument-box",
  size = "sm",
  interactive = false,
  className = "",
  onClick,
  ...props
}: SignalTagProps) {
  const normKey = String(signal).toUpperCase().trim();
  const cfg = SIGNAL_CONFIG[normKey] || {
    label: normKey,
    dotColor: "#5f6b76",
    className: "bg-slate-100 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300",
  };

  const sizeClass =
    size === "xs"
      ? "text-[10px] px-1.5 py-0.5 leading-none"
      : size === "md"
      ? "text-xs px-2.5 py-1 leading-normal"
      : "text-[11px] px-2 py-0.5 leading-tight";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[var(--radius-sm,4px)] font-mono font-medium tracking-wide uppercase select-none shrink-0 ${cfg.className} ${sizeClass} ${
        interactive ? "cursor-pointer hover:opacity-85 focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]" : ""
      } ${className}`}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onClick}
      data-signal-provenance={normKey}
      {...props}
    >
      <span
        className="w-1.5 h-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: cfg.dotColor }}
        aria-hidden="true"
      />
      <span>{cfg.label}</span>
    </span>
  );
}
