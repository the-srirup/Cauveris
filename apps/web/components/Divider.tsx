"use client";

import { forwardRef, type HTMLAttributes } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const dividerStyles = tv({
  base: `
    border-0 bg-[var(--color-border)]
    transition-colors duration-150
  `,
  variants: {
    orientation: {
      horizontal: "w-full h-px",
      vertical: "h-full w-px",
    },
    variant: {
      default: "",
      dashed: "border-t-[1px] border-dashed border-[var(--color-border)]",
      dotted: "border-t-[1px] border-dotted border-[var(--color-border)]",
      strong: "bg-[var(--color-border-strong)] h-[2px]",
    },
    spacing: {
      none: "",
      sm: "my-2",
      md: "my-4",
      lg: "my-6",
    },
  },
  defaultVariants: {
    orientation: "horizontal",
    variant: "default",
    spacing: "none",
  },
});

export interface DividerProps
  extends Omit<HTMLAttributes<HTMLDivElement>, "role">,
    VariantProps<typeof dividerStyles> {
  children?: React.ReactNode;
}

export const Divider = forwardRef<HTMLDivElement, DividerProps>(
  (
    {
      orientation = "horizontal",
      variant = "default",
      spacing = "none",
      children,
      className,
      ...props
    },
    ref
  ) => {
    // Horizontal with label
    if (children && orientation === "horizontal") {
      return (
        <div className="flex items-center gap-3 w-full" {...props}>
          <div
            ref={ref}
            role="separator"
            aria-orientation="horizontal"
            className={dividerStyles({ orientation, variant, spacing: "none", className: "flex-1" })}
          />
          <span className="text-xs text-[var(--color-text-muted)] uppercase tracking-wider flex-shrink-0 px-2">
            {children}
          </span>
          <div
            role="separator"
            aria-orientation="horizontal"
            className={dividerStyles({ orientation, variant, spacing: "none", className: "flex-1" })}
          />
        </div>
      );
    }

    return (
      <div
        ref={ref}
        role="separator"
        aria-orientation={orientation}
        className={dividerStyles({ orientation, variant, spacing, className })}
        {...props}
      />
    );
  }
);

Divider.displayName = "Divider";