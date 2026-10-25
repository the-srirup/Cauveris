"use client";

import type { ReactNode } from "react";

export interface ProgressProps {
  /** Progress value (0-100) */
  value: number;
  /** Visual variant */
  variant?: "default" | "success" | "danger" | "warning" | "done";
  /** Tone alias for backward compatibility */
  tone?: "primary" | "success" | "danger" | "amber" | "secondary" | "accent" | string;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Show value label */
  showLabel?: boolean;
  /** Custom label */
  label?: string;
  /** Additional class names */
  className?: string;
  /** ARIA label */
  "aria-label"?: string;
  /** Whether progress is indeterminate */
  indeterminate?: boolean;
}

export function Progress({
  value,
  variant,
  tone,
  size = "md",
  showLabel = false,
  label,
  className = "",
  "aria-label": ariaLabel,
  indeterminate = false,
}: ProgressProps) {
  const toneMap: Record<string, "default" | "success" | "danger" | "warning" | "done"> = {
    primary: "default",
    success: "success",
    danger: "danger",
    amber: "warning",
    warning: "warning",
    secondary: "warning",
    accent: "default",
    done: "done",
    default: "default",
  };
  const resolvedVariant = variant || (tone ? toneMap[tone] || "default" : "default");
  const variantColors = {
    default: "bg-[var(--color-accent-emphasis)]",
    success: "bg-[var(--color-success-emphasis)]",
    danger: "bg-[var(--color-danger-emphasis)]",
    warning: "bg-[var(--color-attention-emphasis)]",
    done: "bg-[var(--color-done-emphasis)]",
  };

  const sizeStyles = {
    sm: "h-1.5",
    md: "h-2",
    lg: "h-3",
  };

  const clampedValue = Math.min(100, Math.max(0, value));

  return (
    <div
      className={`w-full ${className}`}
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : clampedValue}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
    >
      <div
        className={`
          w-full ${sizeStyles[size]}
          bg-[var(--color-border-muted)]
          rounded-[var(--radius-full)]
          overflow-hidden
        `}
      >
        {indeterminate ? (
          <div
            className={`
              ${variantColors[resolvedVariant]}
              h-full rounded-[var(--radius-full)]
              animate-indeterminate
            `}
            style={{ width: "30%" }}
          />
        ) : (
          <div
            className={`
              ${variantColors[resolvedVariant]}
              h-full rounded-[var(--radius-full)]
              transition-all duration-200 ease-out
            `}
            style={{ width: `${clampedValue}%` }}
          />
        )}
      </div>
      {(showLabel || label) && (
        <div className="mt-1.5 flex items-center justify-between text-xs">
          <span className="text-[var(--color-fg-muted)]">{label || (showLabel ? "" : `${Math.round(clampedValue)}%`)}</span>
          {showLabel && (
            <span className="font-mono text-[var(--color-fg-default)]">{Math.round(clampedValue)}%</span>
          )}
        </div>
      )}
    </div>
  );
}

export interface CircularProgressProps {
  /** Progress value (0-100) */
  value: number;
  /** Size in pixels */
  size?: number;
  /** Stroke width */
  strokeWidth?: number;
  /** Visual variant */
  variant?: "default" | "success" | "danger" | "warning" | "done";
  /** Show value label in center */
  showLabel?: boolean;
  /** Additional class names */
  className?: string;
  /** ARIA label */
  "aria-label"?: string;
}

export function CircularProgress({
  value,
  size = 32,
  strokeWidth = 3,
  variant = "default",
  showLabel = false,
  className = "",
  "aria-label": ariaLabel,
}: CircularProgressProps) {
  const variantColors = {
    default: "var(--color-accent-emphasis)",
    success: "var(--color-success-emphasis)",
    danger: "var(--color-danger-emphasis)",
    warning: "var(--color-attention-emphasis)",
    done: "var(--color-done-emphasis)",
  };

  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clampedValue = Math.min(100, Math.max(0, value));
  const offset = circumference * (1 - clampedValue / 100);

  return (
    <div
      className={`inline-flex items-center justify-center ${className}`}
      role="progressbar"
      aria-valuenow={clampedValue}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={ariaLabel}
      style={{ width: size, height: size }}
    >
      <svg className="transform -rotate-90" width={size} height={size}>
        <circle
          className="text-[var(--color-border-muted)]"
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="none"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        <circle
          className={variantColors[variant]}
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="none"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{
            transition: "stroke-dashoffset 0.3s ease-out",
            transformOrigin: "center",
          }}
        />
      </svg>
      {showLabel && (
        <div className="absolute flex items-center justify-center text-[11px] font-mono font-medium text-[var(--color-fg-default)]">
          {Math.round(clampedValue)}%
        </div>
      )}
    </div>
  );
}