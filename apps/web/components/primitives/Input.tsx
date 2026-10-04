"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const inputStyles = tv({
  base: `
    w-full rounded-lg border border-[var(--color-border)]
    bg-[var(--color-surface)]/80 text-[var(--color-text-primary)]
    placeholder:text-[var(--color-text-muted)]/60
    transition-colors duration-150 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:border-transparent
    disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--color-surface)]/40
    read-only:bg-[var(--color-surface-2)]/40
  `,
  variants: {
    size: {
      sm: `h-8 px-3 text-xs`,
      md: `h-9 px-3.5 text-sm`,
      lg: `h-11 px-4 text-base`,
    },
    state: {
      default: ``,
      error: `border-[var(--color-brand-danger)] focus-visible:ring-[var(--color-brand-danger)]`,
      success: `border-[var(--color-brand-success)] focus-visible:ring-[var(--color-brand-success)]`,
      warning: `border-[var(--color-brand-warning)] focus-visible:ring-[var(--color-brand-warning)]`,
    },
  },
  defaultVariants: {
    size: "md",
    state: "default",
  },
});

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "size">, VariantProps<typeof inputStyles> {
  label?: string;
  hint?: string;
  error?: string;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  leftElement?: ReactNode;
  rightElement?: ReactNode;
  onValueChange?: (value: string) => void;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      hint,
      error,
      leftIcon,
      rightIcon,
      leftElement,
      rightElement,
      size,
      state,
      className,
      id,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const hintId = hint ? `${inputId}-hint` : undefined;
    const errorId = error ? `${inputId}-error` : undefined;
    const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

    const effectiveState = error ? "error" : state;
    const hasLeft = Boolean(leftIcon || leftElement);
    const hasRight = Boolean(rightIcon || rightElement);

    const paddingLeft = hasLeft ? (size === "sm" ? "pl-8" : size === "lg" ? "pl-11" : "pl-9") : "";
    const paddingRight = hasRight ? (size === "sm" ? "pr-8" : size === "lg" ? "pr-11" : "pr-9") : "";

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-xs font-medium text-[var(--color-text-muted)] mb-1.5">
            {label}
          </label>
        )}
        <div className="relative flex items-center w-full">
          {hasLeft && (
            <div className={`absolute ${size === "sm" ? "left-2.5" : "left-3"} top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none flex items-center justify-center`}>
              {leftElement || leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`${inputStyles({
              size,
              state: effectiveState,
            })} ${paddingLeft} ${paddingRight} ${className || ""}`}
            aria-describedby={describedBy}
            aria-invalid={!!error}
            {...props}
          />
          {hasRight && (
            <div className={`absolute ${size === "sm" ? "right-2" : "right-2.5"} top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] flex items-center justify-center z-10`}>
              {rightElement || rightIcon}
            </div>
          )}
        </div>
        {error && (
          <p id={errorId} className="mt-1.5 text-sm text-[var(--color-brand-danger)] flex items-center gap-1.5" role="alert">
            <svg className="h-3.5 w-3.5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={hintId} className="mt-1.5 text-sm text-[var(--color-text-muted)]">
            {hint}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";