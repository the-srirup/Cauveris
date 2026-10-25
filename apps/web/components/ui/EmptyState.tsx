"use client";

import type { ReactNode } from "react";
import { Button } from "./Button";

export interface EmptyStateProps {
  /** Main icon */
  icon?: ReactNode;
  /** Title text */
  title: string;
  /** Description text */
  description?: string;
  /** Primary action */
  action?: ReactNode;
  /** Secondary action */
  secondaryAction?: ReactNode;
  /** Size variant */
  size?: "sm" | "md" | "lg";
  /** Alignment */
  align?: "center" | "left";
  /** Additional class names */
  className?: string;
}

const sizeStyles = {
  sm: "py-6 px-4",
  md: "py-10 px-6",
  lg: "py-16 px-8",
};

const iconSizes = {
  sm: "h-10 w-10",
  md: "h-14 w-14",
  lg: "h-20 w-20",
};

const titleSizes = {
  sm: "text-base",
  md: "text-lg",
  lg: "text-xl",
};

const descSizes = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-lg",
};

export function EmptyState({
  icon,
  title,
  description,
  action,
  secondaryAction,
  size = "md",
  align = "center",
  className = "",
}: EmptyStateProps) {
  const alignClasses = {
    center: "text-center mx-auto",
    left: "text-left",
  };

  return (
    <div className={`empty-state flex flex-col items-center ${alignClasses[align]} ${sizeStyles[size]} ${className}`} role="status" aria-live="polite">
      {icon && (
        <div className={`flex-shrink-0 text-[var(--color-fg-subtle)] opacity-50 ${iconSizes[size]}`} aria-hidden="true">
          {icon}
        </div>
      )}
      <div className="mt-4 max-w-md">
        <h3 className={`font-semibold text-[var(--color-fg-default)] ${titleSizes[size]}`}>{title}</h3>
        {description && (
          <p className={`mt-2 text-[var(--color-fg-muted)] ${descSizes[size]}`}>{description}</p>
        )}
      </div>
      {(action || secondaryAction) && (
        <div className="mt-6 flex items-center justify-center gap-3 flex-wrap">
          {secondaryAction && (
            <Button variant="ghost" size="md">
              {secondaryAction}
            </Button>
          )}
          {action && <Button variant="primary" size="md">{action}</Button>}
        </div>
      )}
    </div>
  );
}

// Predefined empty state icons
export const EmptyStateIcons = {
  search: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M11.742 10.344a6.5 6.5 0 1 1-1.397 1.398h-.001c-.03.04-.092.078-.143.078-.031 0-.062-.009-.091-.03-.03-.02-.055-.046-.078-.08l-.002-.002a1.07 1.07 0 0 0-.017-.035l-3.531-3.531a1 1 0 0 0-.16-.07l.707-.707a1 1 0 0 1 1.414 1.414l-.707.707a1 1 0 0 0 0 1.414l3.53 3.53a1 1 0 1 0 1.504-1.273ZM6.5 10.5A4 4 0 1 0 6.5 2.5a4 4 0 0 0 0 8Z" />
    </svg>
  ),
  folder: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M1.5 2A1.5 1.5 0 0 1 3 0.5h10A1.5 1.5 0 0 1 14.5 2v12a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 14v-12zm13.5 1a.5.5 0 0 0-.969-.206L8 7.168 3.47 3.704a.31.31 0 0 0-.21 0l-.41.401A.31.31 0 0 0 3 4.5v7.09l5.16 2.968a.5.5 0 0 0 .832 0L13 8.5v-5.5zm-2 6.5a.5.5 0 0 1 0-1h-7a.5.5 0 0 1 0 1h7z" />
    </svg>
  ),
  document: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-13a.75.75 0 0 1-.75-.75v-13ZM4.5 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7.25a.75.75 0 0 0-.75-.75H9.5a.75.75 0 0 1 0-1.5h4.75a.75.75 0 0 1 .75.75v1.75a1 1 0 0 1-1 1H4.5a1 1 0 0 1-1-1v-13Z" />
    </svg>
  ),
  database: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M0 3.5A2.5 2.5 0 0 1 2.5 1h11A2.5 2.5 0 0 1 16 3.5v3A2.5 2.5 0 0 1 13.5 9h-11A2.5 2.5 0 0 1 0 6.5v-3zm0 5A2.5 2.5 0 0 1 2.5 11h11A2.5 2.5 0 0 1 16 13.5v3A2.5 2.5 0 0 1 13.5 19h-11A2.5 2.5 0 0 1 0 16.5v-3zM2.354 3.566a4.501 4.501 0 0 0 0 1.868A5 5 0 0 1 2.5 2.5h11a5 5 0 0 1 0 10h-11a5 5 0 0 1-.146-1.934zM1.5 8a1 1 0 0 0-1 1v3a1 1 0 0 0 1 1h13a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1H1.5z" />
    </svg>
  ),
  network: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="m8 1.784 6.587 3.79a1.5 1.5 0 0 1 1.05 2.371L9.639 14.245a.75.75 0 0 1-.678 0L.362 10.945a1.5 1.5 0 0 1 1.05-2.371L8 1.784zm0 1.154L1.867 5.34a.75.75 0 0 0-.487 1.173L7.75 12.81a.5.5 0 0 0 .5 0L14.62 8.987a.75.75 0 0 0-.487-1.172L8 2.938z" />
      <path d="M6.5 7a1.5 1.5 0 1 1 3 0 1.5 1.5 0 0 1-3 0z" />
    </svg>
  ),
  alert: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0z" />
      <path d="M8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4z" />
      <path d="M8 10a1 1 0 1 1 0-2 1 1 0 0 1 0 2z" />
    </svg>
  ),
  success: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z" />
    </svg>
  ),
  user: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 1.5a5.5 5.5 0 1 1 0 11 5.5 5.5 0 0 1 0-11zM8 2.5a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />
      <path d="M3.5 8.5a5 5 0 0 1 9 0v1H3.5v-1z" />
    </svg>
  ),
  settings: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M16 8.493v-.97c0-.633-.637-1.179-1.38-.9C13.947 6.538 13 5.406 13 4c0-.72-.57-1.304-1.258-1.227a4.487 4.487 0 0 0-.207.982L7.529 1.628a1.04 1.04 0 0 0-.7-.329c-.289 0-.565.112-.767.322l-2.942 2.553-.74-.418A4.526 4.526 0 0 0 2.5 3.68c0 .72.57 1.304 1.258 1.227a4.487 4.487 0 0 0 .207.982l2.273 2.885-2.913 2.93a1.04 1.04 0 0 0 0 1.49l2.159 1.211c.454.254 1.039.254 1.489 0l1.774-1-.835 3.28a.75.75 0 0 0 1.386.462l1.631-1.633a4.5 4.5 0 0 0 .73.73l1.633 1.632a.75.75 0 0 0 .9-.95l-.834-3.28 1.77 1c.45.254 1.036.254 1.49 0l2.158-1.21a1.04 1.04 0 0 0 .336-1.49l-2.914-2.929 2.273-2.885a4.5 4.5 0 0 0 .206-.982A1.26 1.26 0 0 0 15 4c0-1.404-.946-2.538-2.25-2.987a1.04 1.04 0 0 0 .33-1.49L13.027.97a1.04 1.04 0 0 0-.7.33l-3.558 3.09 1.791 3.7c.529 1.095-.023 2.156-1.054 2.532A4.5 4.5 0 0 1 12.5 8a4.5 4.5 0 0 1-5 0 4.5 4.5 0 0 1 .415-1.726c-.085-.58.079-1.131.663-1.42 1.498-.79 3.12-.857 4.392-.208.639.328 1.386-.04 1.617-.778.384-.858.733-1.08 1.1-1.256.5.234 1.11.406 1.51.545a1.15 1.15 0 0 0 .46-.151l1.338 2.802a.75.75 0 0 0 1.463-.334ZM8 10a2 2 0 1 1 0-4 2 2 0 0 1 0 4zm0-2a.75.75 0 0 0 0 1.5.75.75 0 0 0 0-1.5z" />
    </svg>
  ),
  code: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M4.72 1.58a.75.75 0 0 1 1.06 0l3.75 3.75a.75.75 0 0 1 0 1.06l-3.75 3.75a.75.75 0 0 1-1.06-1.06L7.94 8 4.72 4.78a.75.75 0 0 1 0-1.06zm1.06 10.42a.75.75 0 0 0 1.06 0l3.75-3.75a.75.75 0 0 0 0-1.06l-3.75-3.75a.75.75 0 1 0-1.06 1.06L10.06 8l-4.28 4.28a.75.75 0 0 0 0 1.06z" />
      <path d="M2.5 8a1 1 0 0 1 1-1h9a1 1 0 0 1 0 2h-9a1 1 0 0 1-1-1z" />
    </svg>
  ),
  clock: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0z" />
      <path d="M8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4z" />
      <path d="M8 10a1 1 0 1 1 0-2 1 1 0 0 1 0 2z" />
    </svg>
  ),
  bell: (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
      <path d="M8 1.5a6.5 6.5 0 0 1 6.5 6.5v2.5a.75.75 0 0 1-1.5 0v-2.5a5 5 0 1 0-10 0v2.5a.75.75 0 0 1-1.5 0v-2.5A6.5 6.5 0 0 1 8 1.5zm0 12a.75.75 0 0 1 .75-.75h3.5a.75.75 0 0 1 0 1.5h-3.5a.75.75 0 0 1-.75-.75z" />
    </svg>
  ),
} as const;