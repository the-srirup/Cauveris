"use client";

/**
 * WebGL availability gate.
 *
 * Probes for a working WebGL context on the client only (never during SSR),
 * renders an accessible fallback when unavailable, and wraps children in a
 * webgl-category error boundary so a context-creation or render failure inside
 * a Three.js canvas degrades to the fallback instead of crashing the page.
 */

import React, { useEffect, useState, type ReactNode } from "react";
import { Box } from "lucide-react";
import { ErrorBoundary } from "@/components/ErrorBoundary";

export function isWebGLSupported(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    const gl =
      canvas.getContext("webgl2") ??
      canvas.getContext("webgl") ??
      canvas.getContext("experimental-webgl");
    return Boolean(gl);
  } catch {
    return false;
  }
}

export function WebGLFallback({ reason }: { reason?: string }) {
  return (
    <div
      role="img"
      aria-label="3D visualization unavailable"
      data-webgl-state="unavailable"
      className="flex h-full min-h-64 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-[var(--divider,#27272a)] bg-[var(--panel-recessed,#0e0e11)] p-6 text-center"
    >
      <Box className="h-6 w-6 text-[var(--text-tertiary,#71717a)]" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--text-secondary,#a1a1aa)]">
        3D visualization unavailable
      </p>
      <p className="max-w-sm text-xs leading-relaxed text-[var(--text-tertiary,#71717a)]">
        {reason ??
          "This browser or device does not provide a WebGL context, so the 3D view cannot be rendered. " +
            "All tables, lists, and text views on this page remain available."}
      </p>
    </div>
  );
}

export interface WebGLGateProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export function WebGLGate({ children, fallback }: WebGLGateProps) {
  // null = not probed yet (SSR / first paint). Probe only on the client.
  const [supported, setSupported] = useState<boolean | null>(null);

  useEffect(() => {
    setSupported(isWebGLSupported());
  }, []);

  if (supported === false) {
    return <>{fallback ?? <WebGLFallback />}</>;
  }

  return (
    <ErrorBoundary category="webgl" fallback={fallback ?? <WebGLFallback reason="The 3D view failed to start. All data views on this page remain available." />}>
      {/* Render nothing heavy until the probe has run on the client. */}
      {supported === null ? null : children}
    </ErrorBoundary>
  );
}

export default WebGLGate;
