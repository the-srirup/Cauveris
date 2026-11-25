"use client";

import { useEffect, useRef, useState } from "react";
import { Activity as ActivityIcon, AlertTriangle, CheckCircle2, Info, Trash2, X } from "lucide-react";
import { useShell, type Activity } from "@/lib/useShell";
import { Tooltip } from "@/components/ui";

function formatEventTime(ts: number): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return "";
  }
}

function getActivityTone(type: Activity["type"]) {
  switch (type) {
    case "error":
      return { icon: AlertTriangle, color: "text-[var(--color-danger-fg,#f85149)]" };
    case "warning":
      return { icon: AlertTriangle, color: "text-[var(--color-attention-fg,#d29922)]" };
    case "pipeline":
      return { icon: CheckCircle2, color: "text-[var(--color-accent-fg,#58a6ff)]" };
    default:
      return { icon: Info, color: "text-[var(--color-fg-muted)]" };
  }
}

/**
 * Live session event and audit feed popover in the top navbar.
 * Replaces decorative mode toggles with real operational telemetry from useShell().
 */
export function ActivityFeedButton() {
  const { state, removeActivity, clearActivities } = useShell();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const activities = state.activities ?? [];

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative">
      <Tooltip content={`Session activity (${activities.length})`} position="bottom">
        <button
          type="button"
          onClick={() => setOpen((prev) => !prev)}
          aria-label="Session activity log"
          aria-expanded={open}
          aria-haspopup="dialog"
          className={`relative inline-flex items-center justify-center h-8.5 w-8.5 rounded-[var(--radius-sm,4px)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${
            open
              ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)]"
              : "bg-[var(--color-canvas-muted)]/65 dark:bg-[var(--color-canvas-muted)] text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-muted)] dark:hover:bg-[var(--color-border-default)]"
          }`}
        >
          <ActivityIcon className="h-4 w-4" aria-hidden="true" />
          {activities.length > 0 && (
            <span
              className="absolute top-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-[var(--color-accent-fg,#58a6ff)]"
              aria-hidden="true"
            />
          )}
        </button>
      </Tooltip>

      {open && (
        <div
          className="absolute right-0 top-full mt-1.5 w-80 sm:w-96 rounded-[var(--radius-lg,8px)] bg-[var(--surface-rail,var(--color-canvas-default))] shadow-[var(--shadow-xl),inset_0_1px_0_rgba(255,255,255,0.06)] z-[var(--z-dropdown,30)] overflow-hidden"
          role="dialog"
          aria-label="Session activity log"
        >
          <div className="flex items-center justify-between px-3.5 py-2.5 bg-[var(--surface-card,var(--color-canvas-inset))]">
            <span className="text-xs font-semibold text-[var(--color-fg-default)]">
              Session Activity
            </span>
            {activities.length > 0 && typeof clearActivities === "function" && (
              <button
                type="button"
                onClick={() => clearActivities()}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] transition-colors"
              >
                <Trash2 className="h-3 w-3" />
                <span>Clear</span>
              </button>
            )}
          </div>

          <div className="max-h-72 overflow-y-auto p-1.5 space-y-1">
            {activities.length === 0 ? (
              <div className="py-8 px-4 text-center text-xs text-[var(--color-fg-muted)]">
                No session events recorded yet. Actions such as pipeline runs, incident switches, and exports appear here.
              </div>
            ) : (
              activities.map((item) => {
                const tone = getActivityTone(item.type);
                const Icon = tone.icon;
                return (
                  <div
                    key={item.id}
                    className="group flex items-start gap-2.5 px-2.5 py-2 rounded-[var(--radius-sm,4px)] bg-[var(--surface-card)]/60 hover:bg-[var(--surface-tile)] transition-colors"
                  >
                    <Icon className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${tone.color}`} aria-hidden="true" />
                    <div className="min-w-0 flex-1">
                      <p className="text-xs text-[var(--color-fg-default)] leading-snug break-words">
                        {item.message}
                      </p>
                      <p className="mt-0.5 font-mono text-[10px] text-[var(--color-fg-subtle)]">
                        {formatEventTime(item.timestamp)}
                        {item.stageId ? ` • ${item.stageId}` : ""}
                      </p>
                    </div>
                    {item.dismissible && typeof removeActivity === "function" && (
                      <button
                        type="button"
                        onClick={() => removeActivity(item.id)}
                        aria-label="Dismiss activity item"
                        className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--color-fg-subtle)] hover:text-[var(--color-fg-default)] transition-opacity"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ActivityFeedButton;
