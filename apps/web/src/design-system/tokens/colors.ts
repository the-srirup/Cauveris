/**
 * CAUVERIS SYSTEMS WORKBENCH - Design Tokens: Colors
 * Precision Monotone Engineering Palette for autonomous-system failures.
 */

export const SURFACES = {
  canvas: "#09090b", // Deep neutral black
  workspace: "#121215", // Dark neutral charcoal
  panel: "#18181b", // Neutral zinc-900 surface
  panelRaised: "#27272a", // Elevated neutral surface
  panelRecessed: "#0e0e11", // Recessed analytical surface
  divider: "#27272a", // Structural neutral line
  dividerStrong: "#3f3f46", // High-confidence separator
} as const;

export const TEXT = {
  primary: "#f4f4f5", // Zinc-100 crisp text
  secondary: "#a1a1aa", // Zinc-400 neutral gray
  tertiary: "#71717a", // Zinc-500 subdued metadata
  inverse: "#09090b", // Zinc-950 near-black
  disabled: "#52525b", // Zinc-600 accessible muted
} as const;

export const SIGNALS = {
  observed: "#f4f4f5", // Crisp light gray
  declared: "#e4e4e7", // Neutral zinc
  derived: "#d4d4d8", // Medium light gray
  calibrated: "#a1a1aa", // Mid gray
  inferred: "#d4d4d8", // Neutral zinc
  simulated: "#a1a1aa", // Mid gray
  verified: "#f4f4f5", // Light gray
  warning: "#a1a1aa", // Subdued gray
  failure: "#e4e4e7", // Neutral zinc
  unknown: "#71717a", // Subdued gray
  sample: "#a1a1aa", // Neutral gray
} as const;

export type SignalType = keyof typeof SIGNALS;
export type SurfaceType = keyof typeof SURFACES;
export type TextType = keyof typeof TEXT;
