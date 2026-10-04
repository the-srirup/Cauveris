"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { tv } from "tailwind-variants";
import { ChevronUp, ChevronDown, X, Filter, Trash2, Search, Zap, FlaskConical, Database, AlertTriangle, AlertCircle, Clock } from "lucide-react";
import { Button, Badge } from "./ui";
import { Divider } from "./Divider";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import type { Activity, ActivityType, TrayState } from "@/lib/useShell";

const trayStyles = tv({
  base: `
    bg-[var(--theme-background)]/95 backdrop-blur-xl border-t border-[var(--color-border)]
    flex flex-col transition-all duration-300 ease-out
    overflow-hidden w-full
  `,
  variants: {
    state: {
      closed: "h-[32px]",
      expanded: "h-[320px] max-h-[60vh]",
    },
  },
  defaultVariants: {
    state: "closed",
  },
});

const handleStyles = tv({
  base: `
    flex h-full items-center justify-between px-4
    cursor-pointer select-none border-t border-[var(--color-border)]
    bg-[var(--color-surface)]/60 backdrop-blur-sm
    transition-colors duration-150
    hover:bg-[var(--color-surface)]
  `,
});

const contentStyles = tv({
  base: `
    overflow-hidden transition-all duration-300 ease-out
  `,
  variants: {
    state: {
      closed: "h-0 opacity-0",
      expanded: "flex-1 opacity-100 overflow-y-auto",
    },
  },
  defaultVariants: {
    state: "closed",
  },
});

const activityItemStyles = tv({
  base: `
    flex items-start gap-3 px-4 py-2 text-sm
    border-b border-[var(--color-border)] last:border-b-0
    hover:bg-[var(--color-surface)] transition-colors
  `,
  variants: {
    type: {
      pipeline: "text-[var(--color-accent)]",
      experiment: "text-secondary",
      system: "text-[var(--color-text-muted)]",
      warning: "text-secondary",
      error: "text-danger",
    },
  },
  defaultVariants: {
    type: "system",
  },
});

const filterStyles = tv({
  base: `
    flex items-center gap-2 px-4 py-2 border-b border-[var(--color-border)]
    bg-surface/60 backdrop-blur-sm
  `,
});

const emptyStyles = tv({
  base: `
    flex flex-col items-center justify-center h-full min-h-[120px] gap-3
    text-center px-6 text-[var(--color-text-muted)]
  `,
});

const groupedActivityStyles = tv({
  base: `
    space-y-1
  `,
});

export function BottomActivityTray() {
  const {
    state: { trayState, activities },
    setTrayState,
    clearActivities,
    removeActivity,
  } = useShell();
  const [filter, setFilter] = useState<ActivityType | "all">("all");
  const [search, setSearch] = useState("");
  const [groupByType, setGroupByType] = useState(false);

  // Filter activities
  const filteredActivities = activities.filter((a) => {
    if (filter !== "all" && a.type !== filter) return false;
    if (search) {
      const haystack = `${a.message} ${a.details || ""}`.toLowerCase();
      if (!haystack.includes(search.toLowerCase())) return false;
    }
    return true;
  });

  // Group by type
  const grouped = useMemo(() => {
    if (!groupByType) return null;
    const groups: Record<ActivityType, Activity[]> = {
      pipeline: [],
      experiment: [],
      system: [],
      warning: [],
      error: [],
    };
    filteredActivities.forEach((a) => groups[a.type].push(a));
    return groups;
  }, [filteredActivities, groupByType]);

  // Settings persistence
  useEffect(() => {
    const saved = localStorage.getItem("cauveris-tray-settings");
    if (saved) {
      try {
        const { filter: f, groupByType: g } = JSON.parse(saved);
        setFilter(f);
        setGroupByType(g);
      } catch {}
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("cauveris-tray-settings", JSON.stringify({ filter, groupByType }));
  }, [filter, groupByType]);

  const toggleTray = useCallback(() => {
    setTrayState(trayState === "closed" ? "expanded" : "closed");
  }, [trayState, setTrayState]);

  const getTypeConfig = (type: ActivityType) => {
    const configs = {
      pipeline: { icon: Zap, label: "Pipeline", badgeTone: "primary" as const },
      experiment: { icon: FlaskConical, label: "Experiment", badgeTone: "secondary" as const },
      system: { icon: Database, label: "System", badgeTone: "muted" as const },
      warning: { icon: AlertTriangle, label: "Warning", badgeTone: "amber" as const },
      error: { icon: AlertCircle, label: "Error", badgeTone: "danger" as const },
    };
    return configs[type];
  };

  const HandleIcon = trayState === "closed" ? ChevronUp : ChevronDown;

  // Utility function for formatting time
  function formatTime(timestamp: number): string {
    const date = new Date(timestamp);
    const now = Date.now();
    const diff = now - timestamp;
    if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  return (
    <aside
      className={trayStyles({ state: trayState })}
      role="region"
      aria-label="Activity tray"
      aria-expanded={trayState === "expanded"}
    >
      {/* Handle / Header - Always visible */}
      <div
        className={handleStyles()}
        onClick={toggleTray}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleTray();
          }
        }}
        aria-label={`Activity tray, currently ${trayState}. Click to ${trayState === "closed" ? "expand" : "collapse"}.`}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-6 w-6 items-center justify-center rounded bg-[var(--color-accent)]/10 text-[var(--color-accent)]">
            <Zap className="h-3.5 w-3.5" />
          </div>
          <span className="font-medium text-sm text-[var(--color-text-primary)]">Activity</span>
          <Badge tone="muted" className="text-[10px]">{activities.length}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <HandleIcon className="h-4 w-4 text-[var(--color-text-muted)] transition-transform duration-200" />
        </div>
      </div>

      {/* Content - Only rendered when expanded, slides down smoothly */}
      <div className={contentStyles({ state: trayState })}>
        {trayState === "expanded" && (
          <>
            {/* Filter Bar */}
            <div className={filterStyles()}>
              <div className="flex items-center gap-2 flex-1">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-text-muted)] pointer-events-none" />
                  <input
                    type="text"
                    placeholder="Filter activities..."
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    className="w-full pl-8 pr-3 h-8 bg-[var(--color-surface-2)]/60 border border-[var(--color-border)] rounded-lg text-xs text-[var(--color-text-primary)] placeholder:text-[var(--color-text-muted)]/60 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] focus:border-transparent transition-all"
                  />
                </div>
                <Divider orientation="vertical" className="h-6" />
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as any)}
                  className="h-8 px-2.5 bg-[var(--color-surface-2)]/60 border border-[var(--color-border)] rounded-lg text-xs text-[var(--color-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] transition-all"
                  aria-label="Filter by type"
                >
                  <option value="all">All</option>
                  <option value="pipeline">Pipeline</option>
                  <option value="experiment">Experiment</option>
                  <option value="system">System</option>
                  <option value="warning">Warnings</option>
                  <option value="error">Errors</option>
                </select>
                <Tooltip content="Group by type" position="top">
                  <button
                    onClick={() => setGroupByType(!groupByType)}
                    className={`inline-flex h-8 w-8 items-center justify-center rounded-lg transition-colors border border-transparent ${groupByType ? "bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)] border-[var(--color-brand-primary)]/20" : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)] hover:border-[var(--color-border)]"}`}
                    aria-pressed={groupByType}
                    aria-label="Group activities by type"
                  >
                    <Filter className="h-4 w-4" />
                  </button>
                </Tooltip>
                <Tooltip content="Clear all" position="top">
                  <button
                    onClick={clearActivities}
                    disabled={activities.length === 0}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-danger hover:bg-danger/10 hover:border-danger/20 transition-colors border border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
                    aria-label="Clear all activities"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </Tooltip>
              </div>
            </div>

            {/* Activity List */}
            <div className={groupedActivityStyles()} role="log" aria-live="polite" aria-atomic="false">
              {grouped ? (
                Object.entries(grouped).map(([type, items]) => (
                  items.length > 0 && (
                    <div key={type} className="space-y-1">
                      <div className="px-4 py-1.5 flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
                        {(() => {
                          const config = getTypeConfig(type as ActivityType);
                          const Icon = config.icon;
                          const toneClass = config.badgeTone === "primary" ? "text-[var(--color-brand-primary)]" : config.badgeTone === "secondary" ? "text-[var(--color-brand-warning)]" : config.badgeTone === "danger" ? "text-[var(--color-brand-danger)]" : config.badgeTone === "amber" ? "text-[var(--color-brand-warning)]" : "text-[var(--color-text-muted)]";
                          return <Icon className={`h-3.5 w-3.5 ${toneClass}`} />;
                        })()}
                        {getTypeConfig(type as ActivityType).label} ({items.length})
                      </div>
                      {items.map((activity) => (
                        <ActivityItem key={activity.id} activity={activity} onDismiss={() => removeActivity(activity.id)} />
                      ))}
                    </div>
                  )
                ))
              ) : (
                filteredActivities.map((activity) => (
                  <ActivityItem key={activity.id} activity={activity} onDismiss={() => removeActivity(activity.id)} />
                ))
              )}

              {filteredActivities.length === 0 && activities.length > 0 && (
                <div className={emptyStyles()}>
                  <Filter className="h-8 w-8 text-[var(--color-text-muted)]/50" />
                  <span>No activities match your filter</span>
                </div>
              )}

              {activities.length === 0 && (
                <div className={emptyStyles()}>
                  <Clock className="h-8 w-8 text-[var(--color-text-muted)]/50" />
                  <span>No activity yet</span>
                  <span className="text-[11px]">Start an investigation to see pipeline activity</span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

function ActivityItem({ activity, onDismiss }: { activity: Activity; onDismiss: () => void }) {
  const config = {
    pipeline: { icon: Zap, label: "Pipeline" },
    experiment: { icon: FlaskConical, label: "Experiment" },
    system: { icon: Database, label: "System" },
    warning: { icon: AlertTriangle, label: "Warning" },
    error: { icon: AlertCircle, label: "Error" },
  }[activity.type];

  return (
    <div className={activityItemStyles({ type: activity.type })}>
      <div className="flex-shrink-0 mt-0.5">
        <config.icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-[var(--color-text-primary)] truncate">{activity.message}</span>
          {activity.stageId && (
            <Badge tone="muted" className="text-[9px]">{activity.stageId}</Badge>
          )}
          {activity.experimentId && (
            <Badge tone="secondary" className="text-[9px]">{activity.experimentId.slice(0, 8)}</Badge>
          )}
        </div>
        {activity.details && (
          <div className="mt-0.5 text-[11px] text-[var(--color-text-muted)] truncate">{activity.details}</div>
        )}
        <div className="flex items-center gap-2 mt-1 text-[10px] text-[var(--color-text-muted)]/70">
          <span>{formatTime(activity.timestamp)}</span>
          {activity.dismissible && (
            <Tooltip content="Dismiss" position="top">
              <button
                onClick={onDismiss}
                className="flex h-5 w-5 items-center justify-center rounded hover:bg-[var(--color-surface)] hover:text-[var(--color-text-primary)] transition-colors"
                aria-label="Dismiss activity"
              >
                <X className="h-3 w-3" />
              </button>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = Date.now();
  const diff = now - timestamp;
  if (diff < 60000) return `${Math.floor(diff / 1000)}s ago`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}