"use client";

import type { ReactNode } from "react";

export interface ToolbarProps {
  /** Toolbar content */
  children: ReactNode;
  /** Additional class names */
  className?: string;
  /** ARIA label for toolbar */
  "aria-label"?: string;
  /** Border below toolbar */
  bordered?: boolean;
}

export function Toolbar({ children, className = "", "aria-label": ariaLabel, bordered = true }: ToolbarProps) {
  const hasCustomPadding = className.includes("py-");
  const hasCustomWrap = className.includes("flex-nowrap");
  return (
    <div
      role="toolbar"
      aria-label={ariaLabel}
      className={`
        flex ${hasCustomWrap ? "" : "flex-wrap"} items-center gap-2 px-4 ${hasCustomPadding ? "" : "py-2.5"}
        bg-[var(--color-canvas-inset)]
        ${bordered ? "border-b border-[var(--color-border-default)]" : ""}
        ${className}
      `}
    >
      {children}
    </div>
  );
}

export interface ToolbarGroupProps {
  children: ReactNode;
  className?: string;
  /** Whether to show divider before group */
  divider?: boolean;
  /** ARIA label for toolbar group */
  "aria-label"?: string;
  /** ARIA role for toolbar group */
  role?: string;
}

export function ToolbarGroup({ children, className = "", divider = false, "aria-label": ariaLabel, role }: ToolbarGroupProps) {
  return (
    <div
      role={role}
      aria-label={ariaLabel}
      className={`inline-flex items-center gap-1.5 ${divider ? "border-l border-[var(--color-border-default)] pl-3" : ""} ${className}`}
    >
      {children}
    </div>
  );
}

export interface ToolbarItemProps {
  children: ReactNode;
  className?: string;
}

export function ToolbarItem({ children, className = "" }: ToolbarItemProps) {
  return <div className={`inline-flex items-center ${className}`}>{children}</div>;
}

export interface ToolbarSeparatorProps {
  className?: string;
  orientation?: "vertical" | "horizontal";
}

export function ToolbarSeparator({ className = "", orientation = "vertical" }: ToolbarSeparatorProps) {
  if (orientation === "horizontal") {
    return <hr className={`w-full border-0 border-t border-[var(--color-border-default)] my-2 ${className}`} role="separator" />;
  }
  return <div className={`h-5 w-px bg-[var(--color-border-default)] ${className}`} role="separator" />;
}

export interface ToolbarTitleProps {
  children: ReactNode;
  className?: string;
}

export function ToolbarTitle({ children, className = "" }: ToolbarTitleProps) {
  return (
    <span className={`text-sm font-semibold text-[var(--color-fg-default)] ${className}`}>
      {children}
    </span>
  );
}

export interface ToolbarSpacerProps {
  className?: string;
}

export function ToolbarSpacer({ className = "" }: ToolbarSpacerProps) {
  return <div className={`flex-1 ${className}`} />;
}