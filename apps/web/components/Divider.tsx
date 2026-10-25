"use client";

import { Divider as NewDivider, SectionDivider, type DividerProps as NewDividerProps, type SectionDividerProps } from "./ui/Divider";

// Re-export new types
export type { NewDividerProps as DividerProps, SectionDividerProps };

// Re-export new components with backward compatibility
export { NewDivider as Divider, SectionDivider };