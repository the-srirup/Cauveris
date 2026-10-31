"use client";

import React from "react";
import { Server, Activity, HardDrive, Sparkles } from "lucide-react";

export interface SystemStatusData {
  backend: "online" | "degraded" | "offline";
  backendLatencyMs?: number;
  worker: "online" | "busy" | "idle" | "offline";
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
      return "text-emerald-800 bg-emerald-50/60 border-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-300 dark:border-emerald-800";
    }
    if (isAmber(state)) {
      return "text-amber-800 bg-amber-50/60 border-amber-200 dark:bg-amber-950/20 dark:text-amber-300 dark:border-amber-800";
    }
    return "text-rose-800 bg-rose-50/60 border-rose-200 dark:bg-rose-950/20 dark:text-rose-300 dark:border-rose-800";
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
      className={`grid grid-cols-2 sm:grid-cols-5 gap-2.5 border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-default,#ffffff)] p-3 rounded-[var(--radius-lg,8px)] text-xs select-none shadow-xs ${className}`}
      data-system-pulse
      {...props}
    >
      {/* Backend API */}
      <div className={`p-2.5 border rounded-[var(--radius-md,6px)] flex items-center justify-between ${getTone(status.backend)}`}>
        <div className="flex items-center gap-2">
          <Server className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">API</span>
        </div>
        <span className="text-xs font-mono font-medium">
          {status.backend} {status.backendLatencyMs ? `(${status.backendLatencyMs}ms)` : ""}
        </span>
      </div>

      {/* Background Worker */}
      <div className={`p-2.5 border rounded-[var(--radius-md,6px)] flex items-center justify-between ${getTone(status.worker)}`}>
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">WORKER</span>
        </div>
        <span className="text-xs font-mono font-medium capitalize">{status.worker}</span>
      </div>

      {/* Storage & Artifacts */}
      <div className={`p-2.5 border rounded-[var(--radius-md,6px)] flex items-center justify-between ${getTone(status.storage)}`}>
        <div className="flex items-center gap-2">
          <HardDrive className="w-4 h-4 shrink-0" />
          <span className="font-semibold text-xs">STORAGE</span>
        </div>
        <span className="text-xs font-mono font-medium capitalize">{status.storage}</span>
      </div>

      {/* Model Gateway */}
      <div
        className={`p-2.5 border rounded-[var(--radius-md,6px)] flex items-center justify-between cursor-help ${getTone(status.nebiusProvider)}`}
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

      {/* Active Jobs */}
      <div className="p-2.5 border border-[var(--color-border-default,#d9e0e7)] bg-[var(--color-canvas-subtle,#f8f9fa)] rounded-[var(--radius-md,6px)] flex items-center justify-between text-[var(--color-fg-default,#1f2933)]">
        <span className="font-semibold text-xs text-[var(--color-fg-muted,#5f6b76)]">PIPELINE QUEUE</span>
        <span className="text-xs font-mono font-semibold">
          {status.activeJobsCount ? `${status.activeJobsCount} Active` : "Idle"}
        </span>
      </div>
    </div>
  );
}
