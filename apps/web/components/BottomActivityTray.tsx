"use client";

import React, { useState, useEffect, useRef } from "react";
import { ChevronUp, ChevronDown, X, AlertCircle, CheckCircle, Info, Loader2, Trash2, Search } from "lucide-react";
import { useShell } from "@/lib/useShell";
import { Badge, Button } from "./ui";
import { Tooltip } from "./Tooltip";
import { Divider } from "./Divider";

export function BottomActivityTray() {
  const { state, setTrayState, clearActivities, removeActivity } = useShell();
  const [isExpanded, setIsExpanded] = useState(false);
  const [filter, setFilter] = useState<"all" | "pipeline" | "system" | "error" | "warning">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [groupByType, setGroupByType] = useState(false);
  const trayRef = useRef<HTMLDivElement>(null);

  // Sync with shell state
  useEffect(() => {
    setIsExpanded(state.trayState === "expanded");
  }, [state.trayState]);

  const handleTrayStateChange = (expanded: boolean) => {
    setIsExpanded(expanded);
    setTrayState(expanded ? "expanded" : "closed");
  };

  const handleHandleClick = () => {
    handleTrayStateChange(!isExpanded);
  };

  // Filter activities
  const filteredActivities = state.activities.filter((activity) => {
    if (filter !== "all" && activity.type !== filter) return false;
    if (searchQuery && !activity.message.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  // Group activities by type
  const groupedActivities = groupByType
    ? filteredActivities.reduce((acc, activity) => {
        if (!acc[activity.type]) acc[activity.type] = [];
        acc[activity.type].push(activity);
        return acc;
      }, {} as Record<string, typeof filteredActivities>)
    : null;

  const formatTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return "Just now";
    if (minutes < 60) return `${minutes}m ago`;
    if (hours < 24) return `${hours}h ago`;
    return `${days}d ago`;
  };

  const typeIcons = {
    pipeline: <Loader2 className="h-4 w-4 text-[var(--color-accent-fg)] mt-0.5 flex-shrink-0" />,
    system: <CheckCircle className="h-4 w-4 text-[var(--color-success-fg)] mt-0.5 flex-shrink-0" />,
    error: <AlertCircle className="h-4 w-4 text-[var(--color-danger-fg)] mt-0.5 flex-shrink-0" />,
    warning: <Info className="h-4 w-4 text-[var(--color-attention-fg)] mt-0.5 flex-shrink-0" />,
  };

  const typeLabels = {
    pipeline: "Pipeline",
    system: "System",
    error: "Error",
    warning: "Warning",
  };

  return (
    <div
      ref={trayRef}
      className={`
        fixed bottom-0 left-0 right-0 z-[var(--z-modal)]
        bg-[var(--color-canvas)]
        border-t border-[var(--color-border-default)]
        transition-height duration-200 ease-out
        ${isExpanded ? "h-[var(--shell-tray-expanded-height)]" : "h-[var(--shell-tray-closed-height)]"}
      `}
      role="region"
      aria-label="Activity tray"
      aria-expanded={isExpanded}
    >
      {/* Handle */}
      <Tooltip content={isExpanded ? "Collapse activity tray" : "Expand activity tray"} position="top">
        <button
          className={`
            absolute top-0 left-1/2 -translate-x-1/2 w-20 h-2.5
            bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)] border-t-0
            rounded-b-[var(--radius-md)] cursor-pointer flex items-center justify-center
            transition-all duration-200 ease-out
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
          `}
          onClick={handleHandleClick}
          aria-label={isExpanded ? "Activity tray, currently expanded" : "Activity tray, currently closed"}
          aria-expanded={isExpanded}
          role="button"
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 text-[var(--color-fg-muted)]" />
          ) : (
            <ChevronUp className="h-4 w-4 text-[var(--color-fg-muted)]" />
          )}
          {state.activities.length > 0 && (
            <Badge variant="primary" className="ml-1.5 text-[10px]">{state.activities.length}</Badge>
          )}
        </button>
      </Tooltip>

      {/* Content - only render when expanded */}
      {isExpanded && (
        <div className="absolute inset-0 top-[var(--shell-tray-closed-height)] bottom-0 m-4 overflow-hidden flex flex-col pointer-events-none">
          {/* Header */}
          <div className="flex items-center justify-between mb-3 pointer-events-auto">
            <div className="flex items-center gap-4">
              <h3 className="text-sm font-semibold text-[var(--color-fg-default)]">
                Activity Tray
              </h3>
            </div>
            <div className="flex items-center gap-2">
              {state.activities.length > 0 && (
                <Tooltip content="Clear all activities" position="top">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={clearActivities}
                    aria-label="Clear all activities"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </Tooltip>
              )}
            </div>
          </div>

          {/* Filters */}
          <div className="flex flex-wrap gap-2 mb-3 pointer-events-auto">
            <div className="flex-1 min-w-[150px] relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--color-fg-muted)]" />
              <input
                type="text"
                placeholder="Search activities..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="
                  w-full h-8 pl-8 pr-4 bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]
                  rounded-[var(--radius-md)] text-sm text-[var(--color-fg-default)]
                  placeholder:text-[var(--color-fg-subtle)]
                  focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-fg)] focus:border-transparent
                  transition-colors duration-80
                "
              />
            </div>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as typeof filter)}
              className="
                h-8 px-3 bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]
                rounded-[var(--radius-md)] text-sm text-[var(--color-fg-default)]
                focus:outline-none focus:ring-2 focus:ring-[var(--color-accent-fg)] focus:border-transparent
                transition-colors duration-80
              "
              aria-label="Filter by type"
            >
              <option value="all">All Types</option>
              <option value="pipeline">Pipeline</option>
              <option value="system">System</option>
              <option value="error">Error</option>
              <option value="warning">Warning</option>
            </select>
            <label className="flex items-center gap-2 text-sm text-[var(--color-fg-muted)] cursor-pointer">
              <input
                type="checkbox"
                checked={groupByType}
                onChange={(e) => setGroupByType(e.target.checked)}
                className="h-3.5 w-3.5 rounded-[var(--radius-sm)] border-[var(--color-border-default)] text-[var(--color-accent-fg)] focus:ring-2 focus:ring-[var(--color-accent-fg)]"
              />
              Group by type
            </label>
          </div>

          {/* Activity List */}
          <div className="flex-1 overflow-y-auto pointer-events-auto" role="feed" aria-label="Activity feed">
            {groupByType && groupedActivities
              ? Object.entries(groupedActivities).map(([type, activities]) => (
                  <React.Fragment key={type}>
                    {activities.length > 0 && (
                      <div className="flex items-center gap-2 px-2 py-1 text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)]">
                        <span className="flex items-center gap-1.5">
                          {typeIcons[type as keyof typeof typeIcons]}
                          {typeLabels[type as keyof typeof typeLabels]}
                        </span>
                        <span className="text-[var(--color-fg-subtle)]/60">({activities.length})</span>
                      </div>
                    )}
                    {activities.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-12 text-[var(--color-fg-muted)]">
                        <Info className="h-8 w-8 opacity-50" />
                        <p className="mt-2 text-sm">
                          {searchQuery ? `No activities match "${searchQuery}"` : `No ${type} activities`}
                        </p>
                      </div>
                    ) : (
                      activities.map((activity) => (
                        <div
                          key={activity.id}
                          className="flex items-start gap-3 p-3 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors"
                          role="article"
                          aria-label={`${typeLabels[activity.type as keyof typeof typeLabels]} activity: ${activity.message}`}
                        >
                          <div className="flex items-start gap-3 flex-1 min-w-0">
                            {typeIcons[activity.type as keyof typeof typeIcons]}
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-[var(--color-fg-default)]">{activity.message}</p>
                              {activity.details && (
                                <p className="mt-1 text-xs text-[var(--color-fg-muted)]">{activity.details}</p>
                              )}
                              <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--color-fg-muted)]">
                                <span>{formatTime(activity.timestamp)}</span>
                                {activity.stageId && <span>Stage: {activity.stageId}</span>}
                              </div>
                            </div>
                            {activity.dismissible && (
                              <Tooltip content="Dismiss" position="left">
                                <button
                                  onClick={() => removeActivity(activity.id)}
                                  className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors flex-shrink-0"
                                  aria-label={`Dismiss ${activity.message}`}
                                >
                                  <X className="h-3.5 w-3.5" />
                                </button>
                              </Tooltip>
                            )}
                          </div>
                        </div>
                      ))
                    )}
                  </React.Fragment>
                ))
              : filteredActivities.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-[var(--color-fg-muted)]">
                    <Info className="h-8 w-8 opacity-50" />
                    <p className="mt-2 text-sm">
                      {searchQuery ? `No activities match "${searchQuery}"` : filter !== "all" ? `No ${filter} activities` : "No activities"}
                    </p>
                  </div>
                ) : (
                  filteredActivities.map((activity) => (
                    <div
                      key={activity.id}
                      className="flex items-start gap-3 p-3 rounded-[var(--radius-md)] bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors"
                      role="article"
                      aria-label={`${typeLabels[activity.type as keyof typeof typeLabels]} activity: ${activity.message}`}
                    >
                      <div className="flex items-start gap-3 flex-1 min-w-0">
                        {typeIcons[activity.type as keyof typeof typeIcons]}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-[var(--color-fg-default)]">{activity.message}</p>
                          {activity.details && (
                            <p className="mt-1 text-xs text-[var(--color-fg-muted)]">{activity.details}</p>
                          )}
                          <div className="mt-2 flex items-center gap-3 text-[10px] text-[var(--color-fg-muted)]">
                            <span>{formatTime(activity.timestamp)}</span>
                            {activity.stageId && <span>Stage: {activity.stageId}</span>}
                          </div>
                        </div>
                        {activity.dismissible && (
                          <Tooltip content="Dismiss" position="left">
                            <button
                              onClick={() => removeActivity(activity.id)}
                              className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors flex-shrink-0"
                              aria-label={`Dismiss ${activity.message}`}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          </Tooltip>
                        )}
                      </div>
                    </div>
                  ))
                )}
          </div>
        </div>
      )}
    </div>
  );
}