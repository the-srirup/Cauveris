"use client";

import { forwardRef, type InputHTMLAttributes, useId } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const toggleStyles = tv({
  base: `
    relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer items-center rounded-full border-2 border-[var(--color-border-strong)]
    bg-[var(--color-surface-2)]
    transition-all duration-fast ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
    disabled:opacity-50 disabled:cursor-not-allowed
    data-[state=checked]:bg-[var(--color-brand-primary)] data-[state=checked]:border-[var(--color-brand-primary)]
    data-[state=checked]:disabled:bg-[var(--color-brand-primary)]/50 data-[state=checked]:disabled:border-[var(--color-brand-primary)]/50
  `,
  variants: {
    size: {
      sm: `h-5 w-9`,
      md: `h-6 w-11`,
      lg: `h-7 w-13`,
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const thumbStyles = tv({
  base: `
    rounded-full bg-[var(--color-text-primary)] shadow-md
    transition-transform duration-fast ease-out
    data-[state=checked]:translate-x-full
  `,
  variants: {
    size: {
      sm: `h-4 w-4 translate-x-[2px]`,
      md: `h-5 w-5 translate-x-[2px]`,
      lg: `h-6 w-6 translate-x-[2px]`,
    },
  },
  defaultVariants: {
    size: "md",
  },
});

const labelStyles = tv({
  base: `
    ml-3 text-[var(--color-text-primary)] font-medium
    disabled:text-[var(--color-text-muted)]
    select-none cursor-pointer
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
    text-[var(--color-text-muted)] ml-14 mt-0.5
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

export interface ToggleProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size">, VariantProps<typeof toggleStyles> {
  label?: string;
  description?: string;
}

export const Toggle = forwardRef<HTMLInputElement, ToggleProps>(
  (
    {
      label,
      description,
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
    const toggleId = id || generatedId;
    const descriptionId = description ? `${toggleId}-description` : undefined;

    return (
      <label htmlFor={toggleId} className="inline-flex items-start cursor-pointer select-none">
        <input
          ref={ref}
          type="checkbox"
          id={toggleId}
          role="switch"
          className={toggleStyles({ size, className })}
          disabled={disabled}
          required={required}
          aria-describedby={descriptionId}
          {...props}
        />
        <span
          className={thumbStyles({ size })}
          aria-hidden="true"
          data-state={props.checked ? "checked" : "unchecked"}
        />
        {(label || description) && (
          <div className="ml-3 min-w-0">
            {label && <span className={labelStyles({ size })}>{label}</span>}
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

Toggle.displayName = "Toggle";