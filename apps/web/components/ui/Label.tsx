"use client";

import type { LabelHTMLAttributes } from "react";
import { isValidElement, cloneElement } from "react";

export interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  /** Whether the field is required */
  required?: boolean;
  /** Whether the field is disabled (affects label styling) */
  disabled?: boolean;
  /** Additional class names */
  className?: string;
}

export function Label({
  children,
  required = false,
  disabled = false,
  className = "",
  ...props
}: LabelProps) {
  return (
    <label
      className={`
        block text-xs font-medium
        ${disabled ? "text-[var(--color-fg-subtle)]" : "text-[var(--color-fg-muted)]"}
        ${required ? "after:content-['*'] after:ml-1 after:text-[var(--color-danger-fg)]" : ""}
        ${className}
      `}
      {...props}
    >
      {children}
    </label>
  );
}

export interface FormFieldProps {
  /** Field label */
  label?: string;
  /** Whether field is required */
  required?: boolean;
  /** Hint text */
  hint?: string;
  /** Error message */
  error?: string;
  /** Field content (input, select, etc.) */
  children: React.ReactNode;
  /** Additional class names for wrapper */
  className?: string;
}

export function FormField({ label, required, hint, error, children, className = "" }: FormFieldProps) {
  const inputId = `field-${Math.random().toString(36).substr(2, 9)}`;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

  // Inject id and aria-describedby into the child element if it's a valid React element
  const childElement = children;
  const childWithProps = isValidElement(childElement)
    ? cloneElement(childElement as React.ReactElement<any>, {
        id: (childElement.props as { id?: string }).id || inputId,
        "aria-describedby": describedBy,
        "aria-invalid": !!error,
      })
    : childElement;

  return (
    <div className={className}>
      {label && (
        <Label htmlFor={inputId} required={required}>
          {label}
        </Label>
      )}
      {childWithProps}
      {error && (
        <p id={errorId} className="mt-1.5 text-xs text-[var(--color-danger-fg)] flex items-center gap-1.5" role="alert">
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