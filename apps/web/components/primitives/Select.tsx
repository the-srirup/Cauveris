"use client";

import { forwardRef, type SelectHTMLAttributes, type ReactNode, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const selectStyles = tv({
  base: `
    w-full rounded-lg border border-[var(--color-border)]
    bg-[var(--color-surface)]/80 text-[var(--color-text-primary)]
    appearance-none
    transition-colors duration-150 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:border-transparent
    disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--color-surface)]/40
    cursor-pointer
  `,
  variants: {
    size: {
      sm: `h-8 px-3 text-xs pr-8`,
      md: `h-9 px-3.5 text-sm pr-9`,
      lg: `h-11 px-4 text-base pr-10`,
    },
    state: {
      default: ``,
      error: `border-[var(--color-brand-danger)] focus-visible:ring-[var(--color-brand-danger)]`,
      success: `border-[var(--color-brand-success)] focus-visible:ring-[var(--color-brand-success)]`,
    },
  },
  defaultVariants: {
    size: "md",
    state: "default",
  },
});

const chevronDown = (
  <svg className="h-4 w-4 text-[var(--color-text-muted)] pointer-events-none" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size">, VariantProps<typeof selectStyles> {
  label?: string;
  hint?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
  leftIcon?: ReactNode;
  onValueChange?: (value: string) => void;
}

// Props that should NOT be forwarded to the native <select> element
const SELECT_PROPS_TO_OMIT: readonly string[] = ['label', 'hint', 'error', 'options', 'placeholder', 'leftIcon', 'onValueChange', 'className', 'size', 'state'];

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      hint,
      error,
      options,
      placeholder,
      leftIcon,
      size,
      state,
      className,
      id,
      disabled,
      required,
      ...props
    },
    ref
  ) => {
    // Filter out props that shouldn't be passed to the native select
    const nativeProps = Object.fromEntries(
      Object.entries(props).filter(([key]) => !SELECT_PROPS_TO_OMIT.includes(key))
    );
    const generatedId = useId();
    const selectId = id || generatedId;
    const hintId = hint ? `${selectId}-hint` : undefined;
    const errorId = error ? `${selectId}-error` : undefined;
    const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

    const effectiveState = error ? "error" : state;

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={selectId} className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">
            {label}
            {required && <span className="text-[var(--color-brand-danger)] ml-1" aria-hidden="true">*</span>}
          </label>
        )}
        <div className="relative">
          {leftIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none flex items-center">
              {leftIcon}
            </div>
          )}
          <select
            ref={ref}
            id={selectId}
            className={selectStyles({
              size,
              state: effectiveState,
              className: className || "",
            })}
            aria-describedby={describedBy}
            aria-invalid={!!error}
            disabled={disabled}
            required={required}
            value={props.value}
            onChange={(e) => {
              if (props.onChange) props.onChange(e);
              if (props.onValueChange) props.onValueChange(e.target.value);
            }}
            {...nativeProps}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--color-text-muted)]">
            {chevronDown}
          </div>
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

Select.displayName = "Select";