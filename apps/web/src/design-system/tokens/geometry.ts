/**
 * CAUVERIS SYSTEMS WORKBENCH - Design Tokens: Geometry
 * Enterprise geometry: 4px small, 6px controls, 8px panels, 10px overlays.
 */

export const RADII = {
  none: "0px",
  sm: "4px", // Small controls, tags & badges
  control: "6px", // Standard interactive buttons & inputs
  panel: "8px", // Panels, cards & containers
  overlay: "10px", // Modals, dialogs & dropdown overlays
  panelLg: "8px",
  controlLg: "6px",
  tab: "4px",
  indicator: "2px",
} as const;

export const BORDERS = {
  fine: "1px solid var(--divider, #d9e0e7)",
  strong: "1px solid var(--divider-strong, #c5ced8)",
  accent: "1px solid var(--color-accent, #0969da)",
  selected: "1px solid var(--color-accent, #0969da)",
} as const;

export const SPACING = {
  railWidth: "56px",
  railExpandedWidth: "220px",
  stripHeight: "44px",
  dockWidth: "360px",
  rowDense: "32px",
  rowStandard: "40px",
} as const;
