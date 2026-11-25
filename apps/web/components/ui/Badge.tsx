"use client";

import { forwardRef, type ReactNode } from "react";

export interface BadgeProps {
  /** Badge content */
  children?: ReactNode;
  /** Visual style variant */
  variant?: "default" | "primary" | "success" | "danger" | "warning" | "done" | "muted";
  /** Tone alias for backward compatibility */
  tone?: "neutral" | "primary" | "success" | "danger" | "amber" | "secondary" | "muted" | "accent" | "default" | "warning" | "done" | string;
  /** Show colored dot indicator */
  dot?: boolean;
  /** Size variant */
  size?: "sm" | "md";
  /** Additional class names */
  className?: string;
  /** On click handler (makes badge interactive) */
  onClick?: () => void;
  /** ARIA label for interactive badges */
  "aria-label"?: string;
}

export const Badge = forwardRef<HTMLElement, BadgeProps>(function Badge(
  {
    children,
    variant,
    tone,
    dot = false,
    size = "md",
    className = "",
    onClick,
    "aria-label": ariaLabel,
  },
  ref
) {
  const toneMap: Record<string, "default" | "primary" | "success" | "danger" | "warning" | "done" | "muted"> = {
    neutral: "default",
    primary: "primary",
    success: "success",
    danger: "danger",
    amber: "warning",
    warning: "warning",
    secondary: "warning",
    muted: "muted",
    accent: "primary",
    done: "done",
    default: "default",
  };

  const resolvedVariant: "default" | "primary" | "success" | "danger" | "warning" | "done" | "muted" =
    variant || (tone ? toneMap[tone] || "default" : "default");

  /*
   * A badge is a state readout, not a button. It reads as an instrument tag:
   * a low-alpha wash of the state hue, a slightly stronger edge in the same
   * hue, and the saturated hue as the label. Neutral states recede (outline)
   * so a coloured state is the only thing that pulls the eye.
   */
  const variantStyles = {
    default: `
      bg-[var(--surface-tile,var(--color-canvas-muted))] text-[var(--color-fg-muted)]
    `,
    primary: `
      bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)]
    `,
    success: `
      bg-[var(--color-success-muted)] text-[var(--color-success-fg)]
    `,
    danger: `
      bg-[var(--color-danger-muted)] text-[var(--color-danger-fg)]
    `,
    warning: `
      bg-[var(--color-attention-muted)] text-[var(--color-attention-fg)]
    `,
    done: `
      bg-[var(--color-done-muted)] text-[var(--color-done-fg)]
    `,
    muted: `
      bg-[var(--surface-tile,var(--color-canvas-muted))] text-[var(--color-fg-muted)]
    `,
  };

  const sizeStyles = {
    sm: "px-1.5 py-0.5 text-[10px]",
    md: "px-2 py-0.5 text-xs",
  };

  const dotColors = {
    default: "bg-[var(--color-fg-muted)]",
    primary: "bg-[var(--color-accent-fg)]",
    success: "bg-[var(--color-success-fg)]",
    danger: "bg-[var(--color-danger-fg)]",
    warning: "bg-[var(--color-attention-fg)]",
    done: "bg-[var(--color-done-fg)]",
    muted: "bg-[var(--color-fg-subtle)]",
  };

  const dotSizes = {
    sm: "h-1 w-1",
    md: "h-1.5 w-1.5",
  };

  const isNeutral = resolvedVariant === "default" || resolvedVariant === "muted";

  const interactiveStyles = isNeutral
    ? "cursor-pointer transition-[border-color,filter,transform] duration-80 hover:border-[var(--color-border-strong)] active:scale-[0.97]"
    : "cursor-pointer transition-[filter,transform] duration-80 hover:brightness-[1.12] active:scale-[0.97]";

  const baseClasses = `
    inline-flex items-center gap-1.5
    font-medium uppercase tracking-[0.06em] leading-none
    rounded-[var(--radius-sm,4px)]
    ${sizeStyles[size]}
    ${variantStyles[resolvedVariant]}
    ${className}
    ${onClick ? interactiveStyles : ""}
  `;

  const dotElement = dot && (
    <span
      className={`
        ${dotSizes[size]} rounded-full flex-shrink-0
        ${dotColors[resolvedVariant]}
      `}
      aria-hidden="true"
    />
  );

  if (onClick) {
    return (
      <button
        ref={ref as React.Ref<HTMLButtonElement>}
        type="button"
        onClick={onClick}
        className={baseClasses}
        aria-label={ariaLabel}
      >
        {dotElement}
        {children}
      </button>
    );
  }

  return (
    <span ref={ref as React.Ref<HTMLSpanElement>} className={baseClasses} role="status" aria-label={ariaLabel}>
      {dotElement}
      {children}
    </span>
  );
});
Badge.displayName = "Badge";

// IssueLabel component for consistent label styling (like GitHub's issue labels)
export interface IssueLabelProps {
  children: ReactNode;
  variant?: "default" | "primary" | "success" | "danger" | "warning" | "done";
  size?: "sm" | "md";
  className?: string;
  onClick?: () => void;
  "aria-label"?: string;
}

export function IssueLabel({
  children,
  variant = "default",
  size = "md",
  className = "",
  onClick,
  "aria-label": ariaLabel,
}: IssueLabelProps) {
  return (
    <Badge variant={variant} size={size} className={className} onClick={onClick} aria-label={ariaLabel}>
      {children}
    </Badge>
  );
}

// Octicon-style icon sizes
export const iconSizes = {
  xs: "h-3 w-3",
  sm: "h-4 w-4",
  md: "h-5 w-5",
  lg: "h-6 w-6",
  xl: "h-8 w-8",
} as const;
