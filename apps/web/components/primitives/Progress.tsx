"use client";

import { tv, type VariantProps } from "tailwind-variants";
import { type ReactNode } from "react";

const progressStyles = tv({
  base: `
    w-full h-1.5 rounded-full bg-[var(--color-surface-2)]
    overflow-hidden
  `,
  variants: {
    size: {
      xs: `h-1`,
      sm: `h-1.5`,
      md: `h-2`,
      lg: `h-3`,
    },
    tone: {
      default: ``,
      primary: ``,
      success: ``,
      danger: ``,
      warning: ``,
      info: ``,
    },
  },
  defaultVariants: {
    size: "md",
    tone: "default",
  },
});

const progressBarStyles = tv({
  base: `
    h-full rounded-full transition-all duration-normal ease-out
    transform-gpu
  `,
  variants: {
    tone: {
      default: `bg-brand-primary`,
      primary: `bg-brand-primary`,
      success: `bg-brand-success`,
      danger: `bg-brand-danger`,
      warning: `bg-brand-warning`,
      info: `bg-brand-info`,
    },
    animated: {
      true: `animate-pulse`,
    },
    striped: {
      true: `bg-gradient-to-r from-current via-transparent to-current bg-[length:20px_100%] animate-[stripe_1s_linear_infinite]`,
    },
  },
  defaultVariants: {
    tone: "default",
    animated: false,
    striped: false,
  },
});

const labelStyles = tv({
  base: `
    flex items-center justify-between text-xs font-medium mb-1.5
  `,
  variants: {
    showValue: {
      true: ``,
      false: ``,
    },
  },
});

export interface ProgressProps extends VariantProps<typeof progressStyles> {
  value: number;
  max?: number;
  min?: number;
  label?: ReactNode;
  valueLabel?: ReactNode;
  showValue?: boolean;
  animated?: boolean;
  striped?: boolean;
  className?: string;
  "aria-label"?: string;
  "aria-valuetext"?: string;
}

export function Progress({
  value,
  max = 100,
  min = 0,
  label,
  valueLabel,
  showValue = true,
  animated,
  striped,
  tone,
  size,
  className,
  "aria-label": ariaLabel,
  "aria-valuetext": ariaValueText,
  ...props
}: ProgressProps) {
  const clampedValue = Math.max(min, Math.min(max, value));
  const percentage = ((clampedValue - min) / (max - min)) * 100;

  const toneColors: Record<string, string> = {
    default: "var(--color-brand-primary)",
    primary: "var(--color-brand-primary)",
    success: "var(--color-brand-success)",
    danger: "var(--color-brand-danger)",
    warning: "var(--color-brand-warning)",
    info: "var(--color-brand-info)",
  };

  return (
    <div className={progressStyles({ tone, size, className })} {...props}>
      {(label || showValue || valueLabel) && (
        <div className={labelStyles({ showValue })}>
          {label && <span className="text-[var(--color-text-secondary)]">{label}</span>}
          {(showValue || valueLabel) && (
            <span className="text-[var(--color-text-primary)] font-mono tabular-nums">
              {valueLabel ?? `${Math.round(percentage)}%`}
            </span>
          )}
        </div>
      )}
      <div
        role="progressbar"
        aria-valuenow={clampedValue}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-label={ariaLabel}
        aria-valuetext={ariaValueText}
        className="relative"
      >
        <div
          className={progressBarStyles({ tone, animated, striped })}
          style={{
            width: `${percentage}%`,
            backgroundColor: toneColors[tone || "primary"],
          }}
        />
      </div>
      <style jsx global>{`
        @keyframes stripe {
          0% { background-position: 0 0; }
          100% { background-position: 20px 0; }
        }
      `}</style>
    </div>
  );
}

Progress.displayName = "Progress";