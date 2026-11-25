"use client";

import type { ReactNode } from "react";

export interface CardProps {
  /** Card title */
  title?: string;
  /** Card subtitle/description */
  subtitle?: string;
  /** Action element (e.g., button) */
  action?: ReactNode;
  /** Card content */
  children: ReactNode;
  /** Additional class names */
  className?: string;
  /** Border accent color */
  borderAccent?: "default" | "primary" | "success" | "danger" | "warning" | "done";
  /** Padding size */
  padding?: "none" | "sm" | "md" | "lg";
  /** Whether card is elevated (more shadow) */
  elevated?: boolean;
  /** Click handler (makes card interactive) */
  onClick?: () => void;
  /** ARIA label for interactive cards */
  "aria-label"?: string;
}

export function Card({
  title,
  subtitle,
  action,
  children,
  className = "",
  borderAccent = "default",
  padding = "md",
  elevated = false,
  onClick,
  "aria-label": ariaLabel,
}: CardProps) {
  const accentRings = {
    default: "",
    primary: "ring-1 ring-[var(--color-accent-muted)]",
    success: "ring-1 ring-[var(--color-success-muted)]",
    danger: "ring-1 ring-[var(--color-danger-muted)]",
    warning: "ring-1 ring-[var(--color-attention-muted)]",
    done: "ring-1 ring-[var(--color-done-muted)]",
  };

  const paddings = {
    none: "p-0",
    sm: "p-4",
    md: "p-5 sm:p-6",
    lg: "p-6 sm:p-8",
  };

  // The rail bleeds to the frame edge, so its own inset has to match the body
  // inset or the two blocks read as misaligned columns.
  const railPaddings = {
    none: "px-5 sm:px-6",
    sm: "px-4",
    md: "px-5 sm:px-6",
    lg: "px-6 sm:px-8",
  };

  const baseClasses = `
    relative flex flex-col
    bg-[var(--surface-card,var(--color-canvas-default))]
    rounded-[var(--radius-lg,8px)]
    shadow-[var(--elevation-card,var(--shadow-sm))]
    ${accentRings[borderAccent]}
    ${elevated ? "shadow-[var(--shadow-md)]" : ""}
    ${
      onClick
        ? "cursor-pointer transition-[background-color,box-shadow,transform] duration-100 ease-out hover:bg-[var(--surface-tile,var(--color-canvas-subtle))] hover:shadow-[var(--shadow-md)]"
        : ""
    }
    ${className}
  `;

  const content = (
    <>
      {(title || action) && (
        <header
          className={`
            flex items-start justify-between gap-3
            rounded-t-[var(--radius-lg,8px)]
            bg-[var(--surface-rail,var(--color-canvas-muted))]
            py-3 ${railPaddings[padding]}
          `}
        >
          <div className="flex-1 min-w-0">
            {title && (
              <h2 className="text-base font-semibold tracking-tight text-[var(--color-fg-default)] truncate">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-0.5 text-xs text-[var(--color-fg-muted)]">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div className={`flex-1 min-w-0 text-[var(--color-fg-default)] ${paddings[padding]}`}>{children}</div>
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={baseClasses}
        aria-label={ariaLabel}
        tabIndex={0}
        role={ariaLabel ? "button" : undefined}
      >
        {content}
      </button>
    );
  }

  return (
    <section className={baseClasses} aria-label={ariaLabel}>
      {content}
    </section>
  );
}

export interface CardHeaderProps {
  children: ReactNode;
  className?: string;
}

export function CardHeader({ children, className = "" }: CardHeaderProps) {
  return <div className={`mb-4 ${className}`}>{children}</div>;
}

export interface CardTitleProps {
  children: ReactNode;
  className?: string;
}

export function CardTitle({ children, className = "" }: CardTitleProps) {
  return <h3 className={`text-base font-semibold tracking-tight text-[var(--color-fg-default)] ${className}`}>{children}</h3>;
}

export interface CardDescriptionProps {
  children: ReactNode;
  className?: string;
}

export function CardDescription({ children, className = "" }: CardDescriptionProps) {
  return <p className={`text-xs text-[var(--color-fg-muted)] mt-1 ${className}`}>{children}</p>;
}

export interface CardContentProps {
  children: ReactNode;
  className?: string;
}

export function CardContent({ children, className = "" }: CardContentProps) {
  return <div className={`space-y-3 ${className}`}>{children}</div>;
}

export interface CardFooterProps {
  children: ReactNode;
  className?: string;
}

export function CardFooter({ children, className = "" }: CardFooterProps) {
  return (
    <div className={`mt-5 pt-4 border-t border-[var(--color-border-default)] flex items-center gap-2.5 ${className}`}>
      {children}
    </div>
  );
}
