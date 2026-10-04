"use client";

import { tv, type VariantProps } from "tailwind-variants";
import { type ReactNode } from "react";

const badgeStyles = tv({
  base: `
    inline-flex items-center gap-1.5
    font-semibold rounded-full px-2.5 py-1
    text-[11px] tracking-wide
    ring-1
    transition-colors duration-fast ease-out
  `,
  variants: {
    tone: {
      neutral: `
        bg-semantic-surface-elevated text-text-muted
        ring-white/10
      `,
      primary: `
        bg-brand-primary/10 text-brand-primary
        ring-brand-primary/25
      `,
      success: `
        bg-brand-success/10 text-brand-success
        ring-brand-success/25
      `,
      danger: `
        bg-brand-danger/10 text-brand-danger
        ring-brand-danger/25
      `,
      warning: `
        bg-brand-warning/10 text-brand-warning
        ring-brand-warning/25
      `,
      info: `
        bg-brand-info/10 text-brand-info
        ring-brand-info/25
      `,
      muted: `
        bg-semantic-surface text-text-muted
        ring-white/5
      `,
      evidence: {
        observed: `
          bg-evidence-observed/10 text-evidence-observed
          ring-evidence-observed/25
        `,
        normalized: `
          bg-evidence-normalized/10 text-evidence-normalized
          ring-evidence-normalized/25
        `,
        inferred: `
          bg-evidence-inferred/10 text-evidence-inferred
          ring-evidence-inferred/25
        `,
        reconstructed: `
          bg-evidence-reconstructed/10 text-evidence-reconstructed
          ring-evidence-reconstructed/25
        `,
        simulated: `
          bg-evidence-simulated/10 text-evidence-simulated
          ring-evidence-simulated/25
        `,
        reproduced: `
          bg-evidence-reproduced/10 text-evidence-reproduced
          ring-evidence-reproduced/25
        `,
        verified: `
          bg-evidence-verified/10 text-evidence-verified
          ring-evidence-verified/25
        `,
        contradicted: `
          bg-evidence-contradicted/10 text-evidence-contradicted
          ring-evidence-contradicted/25
        `,
        unavailable: `
          bg-evidence-unavailable/10 text-evidence-unavailable
          ring-evidence-unavailable/25
        `,
      },
      pipeline: {
        pending: `
          bg-pipeline-pending/10 text-pipeline-pending
          ring-pipeline-pending/25
        `,
        running: `
          bg-pipeline-running/10 text-pipeline-running
          ring-pipeline-running/25
        `,
        completed: `
          bg-pipeline-completed/10 text-pipeline-completed
          ring-pipeline-completed/25
        `,
        failed: `
          bg-pipeline-failed/10 text-pipeline-failed
          ring-pipeline-failed/25
        `,
        warning: `
          bg-pipeline-warning/10 text-pipeline-warning
          ring-pipeline-warning/25
        `,
        cancelled: `
          bg-pipeline-cancelled/10 text-pipeline-cancelled
          ring-pipeline-cancelled/25
        `,
      },
      severity: {
        critical: `
          bg-severity-critical/10 text-severity-critical
          ring-severity-critical/25
        `,
        high: `
          bg-severity-high/10 text-severity-high
          ring-severity-high/25
        `,
        medium: `
          bg-severity-medium/10 text-severity-medium
          ring-severity-medium/25
        `,
        low: `
          bg-severity-low/10 text-severity-low
          ring-severity-low/25
        `,
        info: `
          bg-severity-info/10 text-severity-info
          ring-severity-info/25
        `,
      },
      confidence: {
        veryLow: `
          bg-confidence-veryLow/10 text-confidence-veryLow
          ring-confidence-veryLow/25
        `,
        low: `
          bg-confidence-low/10 text-confidence-low
          ring-confidence-low/25
        `,
        medium: `
          bg-confidence-medium/10 text-confidence-medium
          ring-confidence-medium/25
        `,
        high: `
          bg-confidence-high/10 text-confidence-high
          ring-confidence-high/25
        `,
        veryHigh: `
          bg-confidence-veryHigh/10 text-confidence-veryHigh
          ring-confidence-veryHigh/25
        `,
      },
    },
    dot: {
      true: `pr-1.5`,
      false: ``,
    },
    size: {
      sm: `px-2 py-0.5 text-[10px] gap-1`,
      md: `px-2.5 py-1 text-[11px] gap-1.5`,
      lg: `px-3 py-1.5 text-xs gap-2`,
    },
  },
  defaultVariants: {
    tone: "neutral",
    size: "md",
    dot: false,
  },
  compoundVariants: [
    {
      dot: true,
      className: `
        before:content-[''] before:w-1.5 before:h-1.5 before:rounded-full before:flex-shrink-0
        before:bg-current
      `,
    },
  ],
});

export interface BadgeProps extends VariantProps<typeof badgeStyles> {
  children: ReactNode;
  className?: string;
}

export function Badge({ children, className, ...props }: BadgeProps) {
  return (
    <span className={badgeStyles({ ...props, className })}>{children}</span>
  );
}

Badge.displayName = "Badge";