"use client";

import { forwardRef, useId, type InputHTMLAttributes } from "react";

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size"> {
  /** Label text */
  label?: string;
  /** Hint text */
  hint?: string;
  /** Error message */
  error?: string;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Whether switch is disabled */
  disabled?: boolean;
  /** Additional class names */
  className?: string;
  /** ARIA label */
  "aria-label"?: string;
}

const sizeStyles = {
  sm: {
    track: "h-4 w-7",
    thumb: "h-3 w-3",
    translate: "peer-checked:translate-x-4",
  },
  md: {
    track: "h-5 w-9",
    thumb: "h-4 w-4",
    translate: "peer-checked:translate-x-5",
  },
  lg: {
    track: "h-6 w-11",
    thumb: "h-5 w-5",
    translate: "peer-checked:translate-x-6",
  },
};

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  (
    {
      label,
      hint,
      error,
      size = "md",
      disabled = false,
      className = "",
      id,
      "aria-label": ariaLabel,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const hintId = hint ? `${inputId}-hint` : undefined;
    const errorId = error ? `${inputId}-error` : undefined;
    const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

    const { track, thumb, translate } = sizeStyles[size];

    return (
      <div className={`inline-flex items-start gap-3 ${className}`}>
        <div className="relative flex items-center">
          <input
            ref={ref}
            type="checkbox"
            id={inputId}
            className="sr-only peer"
            disabled={disabled}
            aria-describedby={describedBy}
            aria-invalid={!!error}
            {...props}
          />
          <div
            className={`
              ${track} rounded-full bg-[var(--color-border-muted)]
              peer-focus-visible:outline-none peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--color-accent-fg)] peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-[var(--color-canvas)]
              peer-checked:bg-[var(--color-accent-emphasis)]
              peer-disabled:opacity-50 peer-disabled:cursor-not-allowed
              transition-colors duration-80 ease-out
            `}
            aria-hidden="true"
          />
          <div
            className={`
              absolute top-0.5 left-0.5 ${thumb} rounded-full bg-white shadow-[var(--shadow-sm)]
              ${translate}
              transition-transform duration-80 ease-out
            `}
            aria-hidden="true"
          />
        </div>
        <div className="pt-0.5 min-w-0">
          {label && (
            <label
              htmlFor={inputId}
              className="text-sm font-medium text-[var(--color-fg-default)] cursor-pointer select-none peer-disabled:opacity-50"
            >
              {label}
            </label>
          )}
          {error && (
            <p id={errorId} className="mt-1 text-xs text-[var(--color-danger-fg)]" role="alert">
              {error}
            </p>
          )}
          {hint && !error && (
            <p id={hintId} className="mt-1 text-xs text-[var(--color-fg-subtle)]">
              {hint}
            </p>
          )}
        </div>
      </div>
    );
  }
);

Switch.displayName = "Switch";