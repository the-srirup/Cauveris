/**
 * Color palettes and styling utilities for Holographic Reconstruction
 */

import { NodeType } from "../types";

export const NODE_TYPE_COLORS: Record<string, string> = {
  service: "#3b82f6",       // Blue
  database: "#8b5cf6",      // Purple
  cache: "#06b6d4",         // Cyan
  gateway: "#ec4899",       // Pink
  message_queue: "#84cc16", // Lime
  monitoring: "#f59e0b",    // Amber
  event: "#10b981",         // Emerald
  decision: "#f43f5e",      // Rose
  condition: "#a855f7",     // Violet
  action: "#0ea5e9",        // Sky
};

export function getNodeColor(type: NodeType | string, health: number = 1.0): string {
  const baseColor = NODE_TYPE_COLORS[type] || "#64748b";
  if (health < 0.3) return "#ef4444"; // Red for critical
  if (health < 0.6) return "#f59e0b"; // Amber for degraded
  return baseColor;
}

export function getLinkColor(strength: number, type?: string): string {
  if (type === "network") return "#38bdf8";
  if (strength > 0.7) return "#ef4444";
  if (strength > 0.4) return "#f59e0b";
  return "#64748b";
}

export function hsvToRgb(h: number, s: number, v: number): [number, number, number] {
  const i = Math.floor(h * 6);
  const f = h * 6 - i;
  const p = v * (1 - s);
  const q = v * (1 - f * s);
  const t = v * (1 - (1 - f) * s);

  let r = 0, g = 0, b = 0;
  switch (i % 6) {
    case 0: r = v; g = t; b = p; break;
    case 1: r = q; g = v; b = p; break;
    case 2: r = p; g = v; b = t; break;
    case 3: r = p; g = q; b = v; break;
    case 4: r = t; g = p; b = v; break;
    case 5: r = v; g = p; b = q; break;
  }
  return [r, g, b];
}

/**
 * Viridis colormap approximation for intensity mapping
 */
export function viridis(t: number): [number, number, number] {
  const clamped = Math.max(0, Math.min(1, t));
  const r = Math.max(0, Math.min(1, -0.17 + 1.25 * clamped - 0.28 * clamped * clamped));
  const g = Math.max(0, Math.min(1, 0.05 + 0.9 * clamped + 0.1 * Math.sin(clamped * Math.PI)));
  const b = Math.max(0, Math.min(1, 0.35 + 0.7 * Math.cos((clamped - 0.2) * Math.PI)));
  return [r, g, b];
}
