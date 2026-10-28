"use client";

import React, { useState } from "react";
import { Search, Terminal } from "lucide-react";

export interface CommandAction {
  id: string;
  category: "navigation" | "investigation" | "evidence" | "system";
  title: string;
  shortcut?: string;
  description?: string;
  disabled?: boolean;
  onExecute: () => void;
}

export interface CommandSurfaceProps extends React.HTMLAttributes<HTMLDivElement> {
  actions: CommandAction[];
  isOpen?: boolean;
  onClose?: () => void;
}

export function CommandSurface({
  actions,
  isOpen = true,
  onClose,
  className = "",
  ...props
}: CommandSurfaceProps) {
  const [query, setQuery] = useState("");

  const filtered = actions.filter(
    (a) =>
      a.title.toLowerCase().includes(query.toLowerCase()) ||
      a.category.toLowerCase().includes(query.toLowerCase()) ||
      (a.description && a.description.toLowerCase().includes(query.toLowerCase()))
  );

  return (
    <div
      className={`flex flex-col border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] rounded-[var(--radius-xl,10px)] text-xs shadow-xl select-none overflow-hidden ${className}`}
      data-command-surface
      {...props}
    >
      {/* Input row */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)]">
        <Search className="w-4 h-4 text-[var(--color-fg-muted,#5f6b76)] shrink-0" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type an incident action or search artifacts..."
          className="flex-1 bg-transparent border-none text-[var(--color-fg-default,#1f2933)] placeholder:text-[var(--color-fg-subtle,#7b8794)] focus:outline-none text-sm font-sans"
          autoFocus
        />
        {query && (
          <button
            onClick={() => setQuery("")}
            className="text-xs text-[var(--color-fg-muted,#5f6b76)] hover:text-[var(--color-fg-default,#1f2933)] font-medium"
          >
            Clear
          </button>
        )}
      </div>

      {/* Action List */}
      <div className="divide-y divide-[var(--color-border-default,#d9e0e7)] max-h-[320px] overflow-y-auto bg-[var(--color-canvas-default,#ffffff)]">
        {filtered.length === 0 ? (
          <div className="p-6 text-center text-xs text-[var(--color-fg-muted,#5f6b76)] italic font-sans">
            No operational commands match "{query}"
          </div>
        ) : (
          filtered.map((action) => (
            <div
              key={action.id}
              onClick={() => {
                if (!action.disabled) {
                  action.onExecute();
                  onClose?.();
                }
              }}
              role="button"
              tabIndex={action.disabled ? -1 : 0}
              className={`flex items-center justify-between px-4 py-3 transition-colors ${
                action.disabled
                  ? "opacity-50 cursor-not-allowed bg-[var(--color-canvas-subtle,#f8f9fa)]"
                  : "hover:bg-[var(--color-canvas-subtle,#f8f9fa)] cursor-pointer text-[var(--color-fg-default,#1f2933)]"
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className="text-[10px] font-semibold uppercase text-slate-700 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded-[var(--radius-sm,4px)] shrink-0 font-mono dark:bg-slate-800 dark:border-slate-700 dark:text-slate-300">
                  {action.category}
                </span>
                <span className="font-medium text-xs truncate">{action.title}</span>
                {action.description && (
                  <span className="text-xs text-[var(--color-fg-muted,#5f6b76)] truncate font-sans">
                    {action.description}
                  </span>
                )}
              </div>

              {action.shortcut && (
                <kbd className="ml-2 px-1.5 py-0.5 text-[10px] font-mono text-[var(--color-fg-muted,#5f6b76)] bg-[var(--color-canvas-subtle,#f8f9fa)] border border-[var(--color-border-default,#d9e0e7)] rounded-[var(--radius-sm,4px)] shrink-0">
                  {action.shortcut}
                </kbd>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
