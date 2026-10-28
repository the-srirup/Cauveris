/**
 * CAUVERIS SYSTEMS WORKBENCH - Design Tokens: Motion
 * Restrained, purposeful motion that reveals causality or preserves spatial context.
 * 120-220ms limits. Respects prefers-reduced-motion.
 */

export const MOTION = {
  durationMicro: "100ms",
  durationNormal: "160ms",
  durationTransition: "220ms",
  durationSlow: "300ms",
  easing: "cubic-bezier(0.16, 1, 0.3, 1)",
} as const;
