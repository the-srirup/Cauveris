"use client";

import { Tooltip as NewTooltip, TooltipTrigger, type TooltipProps as NewTooltipProps, type TooltipTriggerProps } from "./ui/Tooltip";

// Re-export new types
export type { NewTooltipProps as TooltipProps, TooltipTriggerProps };

// Re-export new components with backward compatibility
export { NewTooltip as Tooltip, TooltipTrigger };