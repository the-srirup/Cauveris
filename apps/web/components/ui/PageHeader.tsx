"use client";

import type { ReactNode } from "react";
import { Badge } from "./Badge";

export interface PageHeaderProps {
  /** Page title */
  title: string;
  /** Accessible name override for testing/ARIA */
  ariaLabel?: string;
  /** Page subtitle/description */
  description?: string;
  /** Subtitle alias for backward compatibility */
  subtitle?: string;
  /** Badge or status indicator */
  badge?: ReactNode;
  /** Action buttons */
  actions?: ReactNode;
  /** Breadcrumb items */
  breadcrumbs?: Array<{ label: string; href?: string; onClick?: () => void }>;
  /** Additional class names */
  className?: string;
  /** Full width (removes max-width constraint) */
  fullWidth?: boolean;
}

export function PageHeader({
  title,
  ariaLabel,
  description,
  subtitle,
  badge,
  actions,
  breadcrumbs,
  className = "",
  fullWidth = false,
}: PageHeaderProps) {
  const effectiveDescription = description || subtitle;
  return (
    <header className={`page-header w-full ${className}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav className="mb-2 flex items-center gap-1.5 text-sm text-[var(--color-fg-muted)]" aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, index) => (
            <span key={index} className="flex items-center gap-1.5">
              {index > 0 && (
                <svg className="h-3 w-3 flex-shrink-0" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                  <path d="M5.72 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L8.69 8 5.72 5.03a.75.75 0 0 1 0-1.06z" />
                </svg>
              )}
              {crumb.href ? (
                <a href={crumb.href} className="hover:text-[var(--color-fg-default)]">{crumb.label}</a>
              ) : crumb.onClick ? (
                <button onClick={crumb.onClick} className="hover:text-[var(--color-fg-default)] bg-none border-none p-0 cursor-pointer font-inherit">
                  {crumb.label}
                </button>
              ) : (
                <span className="text-[var(--color-fg-default)]" aria-current="page">{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-2">
            <h1
              aria-label={ariaLabel || title}
              className="text-2xl font-semibold text-[var(--color-fg-default)] truncate"
            >
              {title}
            </h1>
            {badge && <div className="flex-shrink-0">{badge}</div>}
          </div>
          {effectiveDescription && (
            <p className="mt-1.5 text-base text-[var(--color-fg-muted)]">{effectiveDescription}</p>
          )}
        </div>
        {actions && (
          <div className="flex-shrink-0 flex items-center gap-2">{actions}</div>
        )}
      </div>
    </header>
  );
}

export interface StatsRowProps {
  /** Stat items */
  children: ReactNode;
  /** Additional class names */
  className?: string;
}

export function StatsRow({ children, className = "" }: StatsRowProps) {
  return (
    <div className={`flex flex-wrap gap-4 ${className}`} role="list" aria-label="Statistics">
      {children}
    </div>
  );
}
