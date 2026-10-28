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
  const borderColors = {
    default: "border-[var(--color-border-default)]",
    primary: "border-l-3 border-l-[var(--color-accent-emphasis)]",
    success: "border-l-3 border-l-[var(--color-success-emphasis)]",
    danger: "border-l-3 border-l-[var(--color-danger-emphasis)]",
    warning: "border-l-3 border-l-[var(--color-attention-emphasis)]",
    done: "border-l-3 border-l-[var(--color-done-emphasis)]",
  };

  const paddings = {
    none: "p-0",
    sm: "p-4",
    md: "p-5 sm:p-6",
    lg: "p-6 sm:p-8",
  };

  const baseClasses = `
    bg-[var(--color-canvas-inset)]
    border border-[var(--color-border-default)]
    rounded-[var(--radius-lg,8px)]
    shadow-xs
    ${elevated ? "hover:shadow-[var(--shadow-md)]" : ""}
    ${onClick ? "cursor-pointer hover:bg-[var(--color-canvas-subtle)]" : ""}
    ${borderColors[borderAccent]}
    ${paddings[padding]}
    ${className}
  `;

  const content = (
    <>
      {(title || action) && (
        <header className="mb-3 flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {title && (
              <h2 className="text-base font-semibold text-[var(--color-fg-default)] truncate">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="mt-0.5 text-sm text-[var(--color-fg-muted)]">
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="flex-shrink-0">{action}</div>}
        </header>
      )}
      <div className="text-[var(--color-fg-default)]">{children}</div>
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
  return <h3 className={`text-base font-semibold text-[var(--color-fg-default)] ${className}`}>{children}</h3>;
}

export interface CardDescriptionProps {
  children: ReactNode;
  className?: string;
}

export function CardDescription({ children, className = "" }: CardDescriptionProps) {
  return <p className={`text-sm text-[var(--color-fg-muted)] mt-1 ${className}`}>{children}</p>;
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