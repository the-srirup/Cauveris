"use client";

import { forwardRef, type InputHTMLAttributes, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const checkboxStyles = tv({
  base: `
    h-4 w-4 rounded border-2 border-[var(--color-border-strong)]
    bg-[var(--theme-background)]
    text-[var(--color-brand-primary)]
    transition-all duration-fast ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
    disabled:opacity-50 disabled:cursor-not-allowed
    checked:bg-[var(--color-brand-primary)] checked:border-[var(--color-brand-primary)]
    checked:disabled:bg-[var(--color-brand-primary)]/50 checked:disabled:border-[var(--color-brand-primary)]/50
    indeterminate:bg-[var(--color-brand-primary)] indeterminate:border-[var(--color-brand-primary)]
  `,
  variants: {
    size: {
      sm: `h-3.5 w-3.5`,
      md: `h-4 w-4`,
      lg: `h-5 w-5`,
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const labelStyles = tv({
  base: `
    inline-flex items-start gap-3 cursor-pointer
    select-none
  `,
  variants: {
    size: {
      sm: `text-sm`,
      md: `text-base`,
      lg: `text-lg`,
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const descriptionStyles = tv({
  base: `
    text-[var(--color-text-muted)]
    mt-1 ml-7
  `,
  variants: {
    size: {
      sm: `text-xs`,
      md: `text-sm`,
      lg: `text-base`,
    },
  },
  defaultVariants: {
    size: "md",
  },
});

export interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size">, VariantProps<typeof checkboxStyles> {
  label?: string;
  description?: string;
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  (
    {
      label,
      description,
      indeterminate,
      size,
      className,
      id,
      disabled,
      required,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const checkboxId = id || generatedId;
    const descriptionId = description ? `${checkboxId}-description` : undefined;

    return (
      <label htmlFor={checkboxId} className={labelStyles({ size })}>
        <input
          ref={ref}
          type="checkbox"
          id={checkboxId}
          className={checkboxStyles({ size, className })}
          disabled={disabled}
          required={required}
          aria-describedby={descriptionId}
          aria-controls={indeterminate ? undefined : undefined}
          {...props}
        />
        {(label || description) && (
          <div className="pt-0.5 min-w-0">
            {label && <span className="text-[var(--color-text-primary)] font-medium">{label}</span>}
            {description && (
              <p id={descriptionId} className={descriptionStyles({ size })}>
                {description}
              </p>
            )}
          </div>
        )}
      </label>
    );
  }
);

Checkbox.displayName = "Checkbox";