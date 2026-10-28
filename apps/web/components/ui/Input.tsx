"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const inputStyles = tv({
  base: `
    w-full rounded-[var(--radius-md,6px)] border border-[var(--color-border-default)]
    bg-[var(--color-canvas)] text-[var(--color-fg-default)]
    placeholder:text-[var(--color-fg-subtle)]
    transition-colors duration-80 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2
    focus-visible:ring-[var(--color-accent-fg)] focus-visible:ring-offset-[var(--color-canvas)]
    focus-visible:border-transparent
    disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--color-canvas-subtle)]
    read-only:bg-[var(--color-canvas-subtle)]
  `,
  variants: {
    size: {
      sm: `h-7.5 px-2.5 text-xs`,
      md: `h-9 px-3 text-sm`,
      lg: `h-11 px-4 text-base`,
    },
    state: {
      default: ``,
      error: `border-[var(--color-danger-emphasis)] focus-visible:ring-[var(--color-danger-emphasis)]`,
      success: `border-[var(--color-success-emphasis)] focus-visible:ring-[var(--color-success-emphasis)]`,
      warning: `border-[var(--color-attention-emphasis)] focus-visible:ring-[var(--color-attention-emphasis)]`,
    },
  },
  defaultVariants: {
    size: "md",
    state: "default",
  },
});

export interface InputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "size">,
    VariantProps<typeof inputStyles> {
  /** Label text */
  label?: string;
  /** Hide label visually (keeps accessible for screen readers) */
  hideLabel?: boolean;
  /** Wrapper class name */
  wrapperClassName?: string;
  /** Hint text */
  hint?: string;
  /** Error message */
  error?: string;
  /** Leading icon */
  leadingIcon?: ReactNode;
  /** Leading icon alias */
  leftIcon?: ReactNode;
  /** Trailing icon */
  trailingIcon?: ReactNode;
  /** Leading element (e.g., prefix) */
  leadingElement?: ReactNode;
  /** Trailing element (e.g., suffix) */
  trailingElement?: ReactNode;
  /** Trailing element alias */
  rightElement?: ReactNode;
  /** Callback on value change */
  onValueChange?: (value: string) => void;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      hideLabel,
      wrapperClassName,
      hint,
      error,
      leadingIcon,
      leftIcon,
      trailingIcon,
      leadingElement,
      trailingElement,
      rightElement,
      size,
      state,
      className,
      id,
      onChange,
      onValueChange,
      "aria-describedby": ariaDescribedBy,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const hintId = hint ? `${inputId}-hint` : undefined;
    const errorId = error ? `${inputId}-error` : undefined;
    const describedBy =
      [hintId, errorId, ariaDescribedBy].filter(Boolean).join(" ") || undefined;

    const effLeadingIcon = leadingIcon || leftIcon;
    const effTrailingElement = trailingElement || rightElement;
    const effectiveState = error ? "error" : state;
    const hasLeading = Boolean(effLeadingIcon || leadingElement);
    const hasTrailing = Boolean(trailingIcon || effTrailingElement);

    const paddingLeft = hasLeading
      ? size === "sm"
        ? "pl-8"
        : size === "lg"
        ? "pl-10"
        : "pl-9"
      : "";
    const paddingRight = hasTrailing
      ? size === "sm"
        ? "pr-8"
        : size === "lg"
        ? "pr-10"
        : "pr-9"
      : "";

    return (
      <div className={wrapperClassName || "w-full"}>
        {label && (
          <label
            htmlFor={inputId}
            className={hideLabel ? "sr-only" : "block text-sm font-medium text-[var(--color-fg-muted)] mb-1.5"}
          >
            {label}
          </label>
        )}
        <div className="relative flex items-center w-full">
          {hasLeading && (
            <div
              className={`
                absolute top-1/2 -translate-y-1/2
                text-[var(--color-fg-muted)] pointer-events-none flex items-center justify-center
                ${size === "sm" ? "left-2" : size === "lg" ? "left-3" : "left-2.5"}
              `}
            >
              {leadingElement || effLeadingIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`${inputStyles({ size, state: effectiveState })} ${paddingLeft} ${paddingRight} ${className || ""}`}
            aria-describedby={describedBy}
            aria-invalid={!!error}
            onChange={(event) => {
              onChange?.(event);
              onValueChange?.(event.target.value);
            }}
            {...props}
          />
          {hasTrailing && (
            <div
              className={`
                absolute top-1/2 -translate-y-1/2
                text-[var(--color-fg-muted)] flex items-center justify-center z-10
                ${size === "sm" ? "right-2" : size === "lg" ? "right-3" : "right-2.5"}
              `}
            >
              {effTrailingElement || trailingIcon}
            </div>
          )}
        </div>
        {error && (
          <p
            id={errorId}
            className="mt-1.5 text-xs text-[var(--color-danger-fg)] flex items-center gap-1.5"
            role="alert"
          >
            <svg className="h-3 w-3 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
              <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zM8 15a7 7 0 1 1 0-14 7 7 0 0 1 0 14z" />
              <path d="M4.5 7.5a.75.75 0 0 1 1.06-1.06l2.94 2.94 6.94-6.94a.75.75 0 1 1 1.06 1.06l-7.5 7.5a.75.75 0 0 1-1.06 0l-3-3a.75.75 0 0 1 0-1.06z" />
            </svg>
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={hintId} className="mt-1.5 text-xs text-[var(--color-fg-subtle)]">
            {hint}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";