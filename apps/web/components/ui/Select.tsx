"use client";

import { forwardRef, type SelectHTMLAttributes, type ReactNode, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const selectStyles = tv({
  base: `
    w-full rounded-[var(--radius-sm)] border border-[var(--color-border-default)]
    bg-[var(--color-canvas)] text-[var(--color-fg-default)]
    appearance-none cursor-pointer
    transition-colors duration-80 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2
    focus-visible:ring-[var(--color-accent-fg)] focus-visible:ring-offset-[var(--color-canvas)]
    focus-visible:border-transparent
    disabled:opacity-50 disabled:cursor-not-allowed disabled:bg-[var(--color-canvas-subtle)]
  `,
  variants: {
    size: {
      sm: `h-6 px-2.5 text-xs pr-8`,
      md: `h-8 px-3 text-sm pr-9`,
      lg: `h-10 px-4 text-sm pr-10`,
    },
    state: {
      default: ``,
      error: `border-[var(--color-danger-emphasis)] focus-visible:ring-[var(--color-danger-emphasis)]`,
      success: `border-[var(--color-success-emphasis)] focus-visible:ring-[var(--color-success-emphasis)]`,
    },
  },
  defaultVariants: {
    size: "md",
    state: "default",
  },
});

const chevronDown = (
  <svg className="h-4 w-4 text-[var(--color-fg-muted)] pointer-events-none" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
    <path d="M4 6l4 4 4-4" />
  </svg>
);

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps
  extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size">,
    VariantProps<typeof selectStyles> {
  label?: string;
  hideLabel?: boolean;
  wrapperClassName?: string;
  hint?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
  leadingIcon?: ReactNode;
  onValueChange?: (value: string) => void;
}

// "onChange" must be omitted here: the native props are spread onto the <select>
// *after* the composed handler below, so a caller-supplied onChange would
// clobber it and `onValueChange` would never fire.
const SELECT_PROPS_TO_OMIT = ["label", "hideLabel", "wrapperClassName", "hint", "error", "options", "placeholder", "leadingIcon", "onValueChange", "onChange", "className", "size", "state"];

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      hideLabel,
      wrapperClassName,
      hint,
      error,
      options,
      placeholder,
      leadingIcon,
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
    const nativeProps = Object.fromEntries(Object.entries(props).filter(([key]) => !SELECT_PROPS_TO_OMIT.includes(key)));
    const generatedId = useId();
    const selectId = id || generatedId;
    const hintId = hint ? `${selectId}-hint` : undefined;
    const errorId = error ? `${selectId}-error` : undefined;
    const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;

    const effectiveState = error ? "error" : state;

    return (
      <div className={wrapperClassName || "w-full"}>
        {label && (
          <label htmlFor={selectId} className={hideLabel ? "sr-only" : "block text-xs font-medium text-[var(--color-fg-muted)] mb-1.5"}>
            {label}
            {required && <span className="text-[var(--color-danger-fg)] ml-1" aria-hidden="true">*</span>}
          </label>
        )}
        <div className="relative">
          {leadingIcon && (
            <div className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-fg-muted)] pointer-events-none flex items-center">
              {leadingIcon}
            </div>
          )}
          <select
            ref={ref}
            id={selectId}
            className={selectStyles({ size, state: effectiveState, className: className || "" })}
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
          <div className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none text-[var(--color-fg-muted)]">
            {chevronDown}
          </div>
        </div>
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
);

Select.displayName = "Select";