"use client";

import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const buttonStyles = tv({
  base: `
    inline-flex items-center justify-center gap-2
    font-medium leading-none whitespace-nowrap select-none
    transition-colors duration-80 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
    disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none
    active:scale-[0.98]
  `,
  variants: {
    variant: {
      primary: `
        bg-[var(--color-accent,#0969da)] text-white
        border border-[var(--color-accent,#0969da)]
        hover:opacity-90
        active:opacity-80
        font-medium shadow-xs
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      secondary: `
        bg-[var(--color-canvas-inset)] text-[var(--color-fg-default)]
        border border-[var(--color-border-default)]
        hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)]
        active:bg-[var(--color-canvas-muted)]
        font-medium shadow-xs
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      danger: `
        bg-[var(--color-danger-emphasis,#cf222e)] text-white
        border border-[var(--color-danger-emphasis,#cf222e)]
        hover:opacity-90
        active:opacity-80
        font-medium shadow-xs
        focus-visible:ring-[var(--color-danger-emphasis)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      ghost: `
        bg-transparent text-[var(--color-fg-default)]
        border border-transparent
        hover:bg-[var(--color-canvas-subtle)]
        active:bg-[var(--color-canvas-muted)]
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      outline: `
        bg-transparent text-[var(--color-fg-default)]
        border border-[var(--color-border-default)]
        hover:bg-[var(--color-canvas-subtle)] hover:border-[var(--color-border-strong)]
        active:bg-[var(--color-canvas-muted)]
        font-medium
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      success: `
        bg-[var(--color-success-emphasis,#1a7f37)] text-white
        border border-[var(--color-success-emphasis,#1a7f37)]
        hover:opacity-90
        active:opacity-80
        font-medium shadow-xs
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
      invisible: `
        bg-transparent text-[var(--color-fg-muted)]
        border border-transparent
        hover:text-[var(--color-fg-default)]
        hover:bg-[var(--color-canvas-subtle)]
        active:bg-[var(--color-canvas-muted)]
        focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-[var(--color-canvas)]
      `,
    },
    size: {
      sm: `
        h-7.5 px-2.5 text-xs
        rounded-[var(--radius-md,6px)]
      `,
      md: `
        h-9 px-3.5 text-sm
        rounded-[var(--radius-md,6px)]
      `,
      lg: `
        h-10.5 px-4.5 text-base
        rounded-[var(--radius-md,6px)]
      `,
    },
  },
  defaultVariants: {
    variant: "secondary",
    size: "md",
  },
  compoundVariants: [
    {
      variant: "primary",
      size: "lg",
      class: "px-5",
    },
  ],
});

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "size">,
    VariantProps<typeof buttonStyles> {
  /** Button content */
  children?: ReactNode;
  /** Show loading spinner */
  loading?: boolean;
  /** Loading text */
  loadingText?: string;
  /** Icon to show before text */
  leadingIcon?: ReactNode;
  /** Icon to show after text */
  trailingIcon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    variant,
    size,
    loading = false,
    loadingText = "Loading...",
    leadingIcon,
    trailingIcon,
    className,
    disabled,
    ...props
  },
  ref
) {
  const isDisabled = disabled || loading;

  return (
    <button
      ref={ref}
      type="button"
      disabled={isDisabled}
      aria-disabled={isDisabled}
      aria-busy={loading}
      className={`${buttonStyles({ variant, size })} ${className || ""}`}
      {...props}
    >
      {loading ? (
        <>
          <svg
            className="h-4 w-4 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className="inline-flex items-center leading-none">{loadingText}</span>
        </>
      ) : (
        <>
          {leadingIcon && (
            <span className="inline-flex items-center justify-center shrink-0" aria-hidden="true">
              {leadingIcon}
            </span>
          )}
          {children !== undefined && children !== null && (
            <span className="inline-flex items-center leading-none">{children}</span>
          )}
          {trailingIcon && (
            <span className="inline-flex items-center justify-center shrink-0" aria-hidden="true">
              {trailingIcon}
            </span>
          )}
        </>
      )}
    </button>
  );
});
Button.displayName = "Button";

// Button Group for grouped actions
export interface ButtonGroupProps {
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
}

export function ButtonGroup({ children, className, "aria-label": ariaLabel }: ButtonGroupProps) {
  return (
    <div
      className={`inline-flex items-center gap-1 rounded-[var(--radius-md)] ${className || ""}`}
      role="group"
      aria-label={ariaLabel}
    >
      {children}
    </div>
  );
}