"use client";

import React from "react";
import { Server, HardDrive, Sparkles } from "lucide-react";

export interface SystemStatusData {
  backend: "online" | "degraded" | "offline";
  backendLatencyMs?: number;
  /**
   * The background worker's state.
   *
   * Not rendered: the worker readout repeated the pipeline status that the
   * top bar already shows, so an idle investigation reported "idle" twice on
   * one screen.  The queue-depth tile below is the honest place for it.
   */
  worker?: "online" | "busy" | "idle" | "offline";
  storage: "healthy" | "warning" | "error";
  nebiusProvider:
    | "live"
    | "fallback"
    | "offline"
    | "NEBIUS_NVIDIA_ACTIVE"
    | "NEBIUS_NVIDIA_DEGRADED"
    | "LOCAL_DETERMINISTIC_ONLY"
    | "PROVIDER_UNAVAILABLE"
    | "CONFIGURATION_INVALID"
    | "RATE_LIMITED"
    | string;
  nebiusModel?: string;
  circuitBreakerState?: "CLOSED" | "OPEN" | "HALF_OPEN" | string;
  lastCallLatencyMs?: number;
  dailyBudgetUsed?: number;
  activeJobsCount?: number;
}

export interface SystemPulseProps extends React.HTMLAttributes<HTMLDivElement> {
  status: SystemStatusData;
  compact?: boolean;
}

export function SystemPulse({
  status,
  compact = false,
  className = "",
  ...props
}: SystemPulseProps) {
  const isGreen = (state: string) =>
    state === "online" ||
    state === "healthy" ||
    state === "live" ||
    state === "idle" ||
    state === "NEBIUS_NVIDIA_ACTIVE";

  const isAmber = (state: string) =>
    state === "degraded" ||
    state === "warning" ||
    state === "fallback" ||
    state === "busy" ||
    state === "LOCAL_DETERMINISTIC_ONLY" ||
    state === "NEBIUS_NVIDIA_DEGRADED";

  const getTone = (state: string) => {
    if (isGreen(state)) {
      return "text-emerald-800 bg-emerald-500/12 dark:bg-emerald-500/12 dark:text-emerald-300";
    }
    if (isAmber(state)) {
      return "text-amber-800 bg-amber-500/12 dark:bg-amber-500/12 dark:text-amber-300";
    }
    return "text-rose-800 bg-rose-500/12 dark:bg-rose-500/12 dark:text-rose-300";
  };

  const getDot = (state: string) => {
    if (isGreen(state)) {
      return "bg-emerald-500";
    }
    if (isAmber(state)) {
      return "bg-amber-500";
    }
    return "bg-rose-500";
  };

  const formatModelLabel = (providerState: string) => {
    if (providerState === "NEBIUS_NVIDIA_ACTIVE" || providerState === "live") {
      return "Nebius NVIDIA";
    }
    if (providerState === "LOCAL_DETERMINISTIC_ONLY" || providerState === "fallback") {
      return "Deterministic";
    }
    if (providerState === "CONFIGURATION_INVALID") {
      return "Config Invalid";
    }
    if (providerState === "PROVIDER_UNAVAILABLE") {
      return "Provider Down";
    }
    if (providerState === "RATE_LIMITED") {
      return "Rate Limited";
    }
    return providerState;
  };

  if (compact) {
    return (
      <div
        className={`flex items-center gap-3 text-xs text-[var(--color-fg-muted,#5f6b76)] select-none ${className}`}
        data-system-pulse
        {...props}
      >
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${getDot(status.backend)}`} />
          <span className="font-medium">
            API: {status.backend} {status.backendLatencyMs ? `(${status.backendLatencyMs}ms)` : ""}
          </span>
        </span>
        <span className="text-[var(--color-border-default,#d9e0e7)]">|</span>
        <span className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${getDot(status.nebiusProvider)}`} />
          <span className="font-medium" title={status.nebiusModel || "Model provider details"}>
            LLM: {formatModelLabel(status.nebiusProvider)}
          </span>
        </span>
      </div>
    );
  }

  const modelTooltip = [
    status.nebiusModel ? `Model: ${status.nebiusModel}` : "Model: not reported by backend",
    `State: ${status.nebiusProvider}`,
    status.circuitBreakerState ? `Circuit: ${status.circuitBreakerState}` : null,
    status.dailyBudgetUsed !== undefined ? `Daily Cost: $${status.dailyBudgetUsed.toFixed(4)}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  return (
    <div
      className={`grid grid-cols-2 sm:grid-cols-4 gap-2.5 bg-[var(--surface-card,var(--color-canvas-default))] p-3 rounded-[var(--radius-lg,8px)] text-xs select-none shadow-[var(--elevation-card)] ${className}`}
      data-system-pulse
      {...props}
    >
      {/* Backend API */}
      <div className={`p-2.5 rounded-[var(--radius-md,6px)] flex items-center justify-between ${getTone(status.backend)}`}>
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">API</span>
        </div>
        <span className="text-xs font-mono font-medium">
          {status.backend} {status.backendLatencyMs ? `(${status.backendLatencyMs}ms)` : ""}
        </span>
      </div>

      {/* Storage & Artifacts */}
      <div className={`p-2.5 rounded-[var(--radius-md,6px)] flex items-center justify-between ${getTone(status.storage)}`}>
        <div className="flex items-center gap-2">
          <HardDrive className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">STORAGE</span>
        </div>
        <span className="text-xs font-mono font-medium capitalize">{status.storage}</span>
      </div>

      {/* Model Gateway */}
      <div
        className={`p-2.5 rounded-[var(--radius-md,6px)] flex items-center justify-between cursor-help ${getTone(status.nebiusProvider)}`}
        title={modelTooltip}
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">MODEL GATEWAY</span>
        </div>
        <div className="flex items-center gap-1.5 font-mono text-xs font-medium truncate max-w-[110px]">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${getDot(status.nebiusProvider)}`} />
          <span className="truncate">{formatModelLabel(status.nebiusProvider)}</span>
        </div>
      </div>

      {/* Queue depth — a count, not a state. "0 queued" cannot be mistaken for
          another pipeline-status readout. */}
      <div className="p-2.5 bg-[var(--surface-tile,var(--color-canvas-subtle))] rounded-[var(--radius-md,6px)] flex items-center justify-between text-[var(--color-fg-default,#1f2933)] shadow-[var(--elevation-tile)]">
        <span className="font-semibold text-xs text-[var(--color-fg-muted,#5f6b76)]">PIPELINE QUEUE</span>
        <span className="text-xs font-mono font-semibold">
          {status.activeJobsCount ? `${status.activeJobsCount} active` : "0 queued"}
        </span>
      </div>
    </div>
  );
}
