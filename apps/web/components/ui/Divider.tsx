"use client";

import type { ReactNode } from "react";

export interface DividerProps {
  /** Divider orientation */
  orientation?: "horizontal" | "vertical";
  /** Label to show in the middle */
  label?: string;
  /** Label position when horizontal */
  labelPosition?: "left" | "center" | "right";
  /** Additional class names */
  className?: string;
}

export function Divider({
  orientation = "horizontal",
  label,
  labelPosition = "center",
  className = "",
}: DividerProps) {
  if (orientation === "vertical") {
    return (
      <div
        className={`h-full w-px bg-[var(--color-border-default)] ${className}`}
        role="separator"
        aria-orientation="vertical"
      />
    );
  }

  if (!label) {
    return (
      <hr
        className={`w-full border-0 border-t border-[var(--color-border-default)] ${className}`}
        role="separator"
        aria-orientation="horizontal"
      />
    );
  }

  const labelPositions = {
    left: "justify-start",
    center: "justify-center",
    right: "justify-end",
  };

  return (
    <div
      className={`flex items-center gap-3 w-full ${className}`}
      role="separator"
      aria-orientation="horizontal"
    >
      <div className="flex-1 h-px bg-[var(--color-border-default)]" />
      <span className={`flex-shrink-0 px-2 text-[10px] font-medium text-[var(--color-fg-subtle)] uppercase tracking-wider ${labelPositions[labelPosition]}`}>
        {label}
      </span>
      <div className="flex-1 h-px bg-[var(--color-border-default)]" />
    </div>
  );
}

export interface SectionDividerProps {
  /** Section title */
  title: string;
  /** Section description */
  description?: string;
  /** Action element */
  action?: ReactNode;
  /** Additional class names */
  className?: string;
}

export function SectionDivider({ title, description, action, className = "" }: SectionDividerProps) {
  return (
    <div className={`flex items-center justify-between py-3 ${className}`}>
      <div>
        <h3 className="text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">
          {title}
        </h3>
        {description && (
          <p className="mt-0.5 text-xs text-[var(--color-fg-subtle)]">{description}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0 ml-4">{action}</div>}
    </div>
  );
}