/**
 * CAUVERIS SYSTEMS WORKBENCH - Design Tokens: Typography
 * Deliberate two-family system: Grotesk UI + High-Precision Monospace.
 */

export const TYPOGRAPHY = {
  fontSans: '"Geist", "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  fontMono: '"Geist Mono", "SFMono-Regular", "Cascadia Code", "Roboto Mono", Consolas, monospace',
  scales: {
    badge: "11px",
    meta: "12px",
    label: "12.5px",
    body: "13.5px",
    subheading: "14px",
    heading: "16px",
    title: "18px",
    instrumentLead: "22px",
  },
} as const;
