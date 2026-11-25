"use client";

import React, { forwardRef } from "react";

export interface InstrumentPanelProps extends Omit<React.HTMLAttributes<HTMLDivElement>, "title"> {
  title?: React.ReactNode;
  subtitle?: React.ReactNode;
  headerRail?: React.ReactNode;
  metadataFooter?: React.ReactNode;
  statusBadge?: React.ReactNode;
  recessed?: boolean;
  raised?: boolean;
  selected?: boolean;
  bordered?: boolean;
  density?: "compact" | "normal" | "spacious";
  actions?: React.ReactNode;
  headerClassName?: string;
  bodyClassName?: string;
}

export const InstrumentPanel = forwardRef<HTMLDivElement, InstrumentPanelProps>(
  (
    {
      title,
      subtitle,
      headerRail,
      metadataFooter,
      statusBadge,
      recessed = false,
      raised = false,
      selected = false,
      bordered = true,
      density = "normal",
      actions,
      className = "",
      headerClassName = "",
      bodyClassName = "",
      children,
      ...props
    },
    ref
  ) => {
    const bgClass = recessed
      ? "bg-[var(--surface-well,var(--color-canvas-subtle))]"
      : raised
      ? "bg-[var(--surface-tile,var(--color-canvas-default))] shadow-[var(--elevation-card)]"
      : "bg-[var(--surface-card,var(--color-canvas-default))] shadow-[var(--elevation-card)]";

    const selectedClass = selected
      ? "ring-2 ring-[var(--color-accent,#0969da)]/60"
      : "";

    const padClass =
      density === "compact"
        ? "p-3"
        : density === "spacious"
        ? "p-6"
        : "p-4 sm:p-5";

    const headerPad =
      density === "compact"
        ? "px-3 py-2"
        : "px-4 sm:px-5 py-3";

    return (
      <div
        ref={ref}
        className={`relative flex flex-col rounded-[var(--radius-lg,8px)] ${selectedClass} ${bgClass} text-[var(--color-fg-default,#1f2933)] transition-colors duration-150 motion-reduce:transition-none overflow-hidden ${className}`}
        data-instrument-panel
        data-selected={selected}
        {...props}
      >
        {/* Header Rail */}
        {(title || headerRail || actions) && (
          <div
            className={`flex items-center justify-between bg-[var(--surface-rail,var(--color-canvas-subtle))] ${headerPad} rounded-t-[var(--radius-lg,8px)] ${headerClassName}`}
          >
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              {headerRail && <div className="shrink-0">{headerRail}</div>}
              {title && (
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="font-sans text-sm font-semibold text-[var(--color-fg-default,#1f2933)] truncate m-0">
                      {title}
                    </h2>
                    {statusBadge && <div className="shrink-0">{statusBadge}</div>}
                  </div>
                  {subtitle && (
                    <div className="text-xs text-[var(--color-fg-muted,#5f6b76)] truncate mt-0.5">
                      {subtitle}
                    </div>
                  )}
                </div>
              )}
            </div>
            {actions && <div className="flex items-center gap-2 shrink-0 ml-3">{actions}</div>}
          </div>
        )}

        {/* Panel Main Work Surface */}
        <div className={`min-w-0 flex-1 ${padClass} ${bodyClassName}`}>
          {children}
        </div>

        {/* Optional Metadata Footer */}
        {metadataFooter && (
          <div className="flex items-center justify-between bg-[var(--surface-rail,var(--color-canvas-subtle))] px-4 py-2.5 text-xs text-[var(--color-fg-muted,#5f6b76)] rounded-b-[var(--radius-lg,8px)]">
            {metadataFooter}
          </div>
        )}
      </div>
    );
  }
);

InstrumentPanel.displayName = "InstrumentPanel";
