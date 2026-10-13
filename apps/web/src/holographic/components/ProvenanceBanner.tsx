"use client";

/**
 * Renders the evidence-provenance record that travels with a reconstruction.
 *
 * Before this existed the page showed a synthetic reconstruction and a real
 * one identically — same layout, same confidence bars, same "Diffraction
 * Online" badge — so an engineer could spend an afternoon diagnosing a
 * fabricated system. This banner is the fix: it is not dismissible when the
 * graph is synthetic, because "this is not your incident" is not a notice,
 * it is a correctness statement about everything below it.
 */

import React, { useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  FileWarning,
  Info,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import type { ProvenanceSeverity, VisualizationMetadata } from "../types";
import { summarizeProvenance } from "../domain/provenance";

const PALETTE: Record<
  ProvenanceSeverity,
  {
    wrapper: string;
    accent: string;
    chip: string;
    Icon: React.ComponentType<{ className?: string }>;
  }
> = {
  critical: {
    wrapper: "bg-rose-500/15 border-rose-500/40",
    accent: "text-rose-300",
    chip: "bg-rose-950/60 border-rose-500/30 text-rose-200",
    Icon: ShieldAlert,
  },
  warning: {
    wrapper: "bg-amber-500/15 border-amber-500/40",
    accent: "text-amber-300",
    chip: "bg-amber-950/60 border-amber-500/30 text-amber-200",
    Icon: AlertTriangle,
  },
  info: {
    wrapper: "bg-emerald-500/10 border-emerald-500/25",
    accent: "text-emerald-300",
    chip: "bg-emerald-950/60 border-emerald-500/25 text-emerald-200",
    Icon: ShieldCheck,
  },
};

function WarningCard({
  code,
  severity,
  message,
  impact,
  remediation,
  chip,
  accent,
}: {
  code: string;
  severity: ProvenanceSeverity;
  message: string;
  impact: string;
  remediation: string;
  chip: string;
  accent: string;
}) {
  const [open, setOpen] = useState(severity === "critical");
  const ToneIcon =
    severity === "critical" ? FileWarning : severity === "warning" ? AlertTriangle : Info;

  return (
    <div className={`rounded-lg border px-3 py-2 ${chip}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2 text-left"
      >
        <ToneIcon className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span className="flex-1 text-[11px] leading-snug">{message}</span>
        <span className="font-mono text-[10px] opacity-60">{code}</span>
        <ChevronDown
          className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && (
        <dl className="mt-2 space-y-1.5 border-t border-current/20 pt-2 text-[11px] leading-snug">
          <div>
            <dt className={`font-semibold ${accent}`}>What this means</dt>
            <dd className="opacity-90">{impact}</dd>
          </div>
          <div>
            <dt className={`font-semibold ${accent}`}>What to do</dt>
            <dd className="opacity-90">{remediation}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

export interface ProvenanceBannerProps {
  metadata?: VisualizationMetadata;
  className?: string;
}

export function ProvenanceBanner({ metadata, className = "" }: ProvenanceBannerProps) {
  const summary = summarizeProvenance(metadata);
  const { wrapper, accent, chip, Icon } = PALETTE[summary.severity];

  return (
    <section
      // `role="status"` and not `alert`: this is standing context about the
      // data on screen, not an interruption. Screen readers should reach it
      // when browsing, not be hijacked by it on every incident switch.
      role="status"
      aria-label="Evidence provenance"
      data-provenance={summary.source}
      className={`rounded-2xl border px-4 py-3 text-xs ${wrapper} ${className}`}
    >
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${accent}`} />
        <div className="min-w-0 flex-1">
          <h3 className={`text-sm font-semibold ${accent}`}>{summary.headline}</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
            {summary.detail}
          </p>

          {summary.facts.length > 0 && (
            <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px]">
              {summary.facts.map((fact) => (
                <div key={fact.label} className="flex items-baseline gap-1.5">
                  <dt className="text-[var(--color-text-muted)]">{fact.label}:</dt>
                  <dd className="truncate text-[var(--color-text-primary)]">{fact.value}</dd>
                </div>
              ))}
            </dl>
          )}

          {summary.warnings.length > 0 && (
            <div className="mt-2.5 space-y-2">
              {summary.warnings.map((w) => (
                <WarningCard
                  key={w.code}
                  code={w.code}
                  severity={w.severity}
                  message={w.message}
                  impact={w.impact}
                  remediation={w.remediation}
                  chip={chip}
                  accent={accent}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
