"use client";

import type { ReactNode } from "react";

export interface KVProps {
  label: string;
  value: ReactNode;
  sub?: string;
  className?: string;
}

export function KV({
  label,
  value,
  sub,
  className = "",
}: KVProps) {
  return (
    <div className={`flex items-center justify-between gap-4 py-2 text-sm border-b border-[var(--color-border-subtle)] last:border-b-0 ${className}`}>
      <div className="min-w-0">
        <span className="text-xs text-[var(--color-fg-muted)]">{label}</span>
        {sub && <span className="block text-[11px] text-[var(--color-fg-subtle)] truncate">{sub}</span>}
      </div>
      <span className="text-right font-mono text-xs font-medium text-[var(--color-fg-default)] shrink-0">
        {value}
      </span>
    </div>
  );
}
