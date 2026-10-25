"use client";

import React, { Children, type ReactNode, type HTMLAttributes, type CSSProperties } from "react";

/**
 * Box - Primitive layout component
 * Similar to Primer's Box component
 */
export interface BoxProps extends HTMLAttributes<HTMLDivElement> {
  /** Display style */
  display?: "block" | "flex" | "inline-flex" | "grid" | "inline-grid" | "inline-block" | "none";
  /** Flex direction */
  flexDirection?: "row" | "column" | "row-reverse" | "column-reverse" | "col" | "col-reverse";
  /** Grid template columns */
  gridTemplateColumns?: string;
  /** Grid template rows */
  gridTemplateRows?: string;
  /** Flex wrap */
  flexWrap?: "wrap" | "nowrap" | "wrap-reverse";
  /** Justify content */
  justifyContent?: "start" | "center" | "end" | "between" | "around" | "evenly";
  /** Align items */
  alignItems?: "start" | "center" | "end" | "stretch" | "baseline";
  /** Gap between children */
  gap?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding */
  p?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding X */
  px?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding Y */
  py?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding top */
  pt?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding right */
  pr?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding bottom */
  pb?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Padding left */
  pl?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Margin */
  m?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin X */
  mx?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin Y */
  my?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin top */
  mt?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin right */
  mr?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin bottom */
  mb?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Margin left */
  ml?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16 | "auto";
  /** Width */
  width?: string | number;
  /** Height */
  height?: string | number;
  /** Min width */
  minWidth?: string | number;
  /** Max width */
  maxWidth?: string | number;
  /** Min height */
  minHeight?: string | number;
  /** Max height */
  maxHeight?: string | number;
  /** Border radius */
  borderRadius?: "none" | "sm" | "md" | "lg" | "xl" | "full";
  /** Border */
  border?: boolean;
  /** Border color */
  borderColor?: "default" | "muted" | "subtle" | "primary" | "success" | "danger" | "warning";
  /** Background */
  background?: "canvas" | "inset" | "subtle" | "muted" | "transparent";
  /** Overflow */
  overflow?: "auto" | "hidden" | "scroll" | "visible";
  /** Position */
  position?: "static" | "relative" | "absolute" | "fixed" | "sticky";
  /** Top */
  top?: string | number;
  /** Right */
  right?: string | number;
  /** Bottom */
  bottom?: string | number;
  /** Left */
  left?: string | number;
  /** Z-index */
  zIndex?: number;
  /** Opacity */
  opacity?: number;
  /** Visibility */
  visibility?: "visible" | "hidden" | "collapse";
  /** Flex */
  flex?: string | number;
  /** Flex grow */
  flexGrow?: number;
  /** Flex shrink */
  flexShrink?: number;
  /** Flex basis */
  flexBasis?: string | number;
  /** Order */
  order?: number;
  /** Align self */
  alignSelf?: "auto" | "start" | "center" | "end" | "stretch" | "baseline";
  /** Justify self */
  justifySelf?: "auto" | "start" | "center" | "end" | "stretch";
}

const spaceMap = {
  0: "var(--space-0)",
  1: "var(--space-1)",
  2: "var(--space-2)",
  3: "var(--space-3)",
  4: "var(--space-4)",
  5: "var(--space-5)",
  6: "var(--space-6)",
  8: "var(--space-8)",
  10: "var(--space-10)",
  12: "var(--space-12)",
  16: "var(--space-16)",
} as const;

const radiusMap = {
  none: "0",
  sm: "var(--radius-sm)",
  md: "var(--radius-md)",
  lg: "var(--radius-lg)",
  xl: "var(--radius-xl)",
  full: "var(--radius-full)",
};

const borderColorMap = {
  default: "var(--color-border-default)",
  muted: "var(--color-border-muted)",
  subtle: "var(--color-border-subtle)",
  primary: "var(--color-accent-emphasis)",
  success: "var(--color-success-emphasis)",
  danger: "var(--color-danger-emphasis)",
  warning: "var(--color-attention-emphasis)",
};

const backgroundMap = {
  canvas: "var(--color-canvas)",
  inset: "var(--color-canvas-inset)",
  subtle: "var(--color-canvas-subtle)",
  muted: "var(--color-canvas-muted)",
  transparent: "transparent",
};

export function Box({
  children,
  display,
  flexDirection,
  flexWrap,
  justifyContent,
  alignItems,
  gap,
  p,
  px,
  py,
  pt,
  pr,
  pb,
  pl,
  m,
  mx,
  my,
  mt,
  mr,
  mb,
  ml,
  width,
  height,
  minWidth,
  maxWidth,
  minHeight,
  maxHeight,
  borderRadius,
  border,
  borderColor,
  background,
  overflow,
  position,
  top,
  right,
  bottom,
  left,
  zIndex,
  opacity,
  visibility,
  flex,
  flexGrow,
  flexShrink,
  flexBasis,
  order,
  alignSelf,
  justifySelf,
  gridTemplateColumns,
  gridTemplateRows,
  className = "",
  style,
  ...props
}: BoxProps) {
  const flexDirMap: Record<string, CSSProperties["flexDirection"]> = {
    col: "column",
    "col-reverse": "column-reverse",
    row: "row",
    "row-reverse": "row-reverse",
    column: "column",
    "column-reverse": "column-reverse",
  };

  const styles: CSSProperties = {
    display,
    flexDirection: flexDirection ? flexDirMap[flexDirection] || (flexDirection as CSSProperties["flexDirection"]) : undefined,
    gridTemplateColumns,
    gridTemplateRows,
    flexWrap,
    justifyContent,
    alignItems,
    gap: gap !== undefined ? spaceMap[gap as keyof typeof spaceMap] : undefined,
    padding: p !== undefined ? spaceMap[p as keyof typeof spaceMap] : undefined,
    paddingLeft: pl !== undefined ? spaceMap[pl as keyof typeof spaceMap] : px !== undefined ? spaceMap[px as keyof typeof spaceMap] : undefined,
    paddingRight: pr !== undefined ? spaceMap[pr as keyof typeof spaceMap] : px !== undefined ? spaceMap[px as keyof typeof spaceMap] : undefined,
    paddingTop: pt !== undefined ? spaceMap[pt as keyof typeof spaceMap] : py !== undefined ? spaceMap[py as keyof typeof spaceMap] : undefined,
    paddingBottom: pb !== undefined ? spaceMap[pb as keyof typeof spaceMap] : py !== undefined ? spaceMap[py as keyof typeof spaceMap] : undefined,
    margin: m !== undefined ? (m === "auto" ? "auto" : spaceMap[m as keyof typeof spaceMap]) : undefined,
    marginLeft: ml !== undefined ? (ml === "auto" ? "auto" : spaceMap[ml as keyof typeof spaceMap]) : mx !== undefined ? (mx === "auto" ? "auto" : spaceMap[mx as keyof typeof spaceMap]) : undefined,
    marginRight: mr !== undefined ? (mr === "auto" ? "auto" : spaceMap[mr as keyof typeof spaceMap]) : mx !== undefined ? (mx === "auto" ? "auto" : spaceMap[mx as keyof typeof spaceMap]) : undefined,
    marginTop: mt !== undefined ? (mt === "auto" ? "auto" : spaceMap[mt as keyof typeof spaceMap]) : my !== undefined ? (my === "auto" ? "auto" : spaceMap[my as keyof typeof spaceMap]) : undefined,
    marginBottom: mb !== undefined ? (mb === "auto" ? "auto" : spaceMap[mb as keyof typeof spaceMap]) : my !== undefined ? (my === "auto" ? "auto" : spaceMap[my as keyof typeof spaceMap]) : undefined,
    width,
    height,
    minWidth,
    maxWidth,
    minHeight,
    maxHeight,
    borderRadius: borderRadius ? radiusMap[borderRadius] : undefined,
    border: border ? "1px solid" : undefined,
    borderColor: borderColor ? borderColorMap[borderColor] : undefined,
    background: background ? backgroundMap[background] : undefined,
    overflow,
    position,
    top,
    right,
    bottom,
    left,
    zIndex,
    opacity,
    visibility,
    flex,
    flexGrow,
    flexShrink,
    flexBasis,
    order,
    alignSelf,
    justifySelf,
    ...style,
  };

  // Remove undefined values
  Object.keys(styles).forEach((key) => {
    if (styles[key as keyof typeof styles] === undefined) {
      delete styles[key as keyof typeof styles];
    }
  });

  return <div className={className} style={styles} {...props}>{children}</div>;
}

/**
 * Flex - Convenience component for flexbox layouts
 */
export interface FlexProps extends BoxProps {
  /** Vertical alignment shorthand */
  verticalAlign?: "top" | "center" | "bottom";
  /** Horizontal alignment shorthand */
  horizontalAlign?: "left" | "center" | "right";
  /** Center both axes */
  center?: boolean;
}

export function Flex({
  children,
  verticalAlign,
  horizontalAlign,
  center,
  className = "",
  style,
  ...props
}: FlexProps) {
  const alignItems = center ? "center" : verticalAlign === "top" ? "start" : verticalAlign === "bottom" ? "end" : verticalAlign === "center" ? "center" : undefined;
  const justifyContent = center ? "center" : horizontalAlign === "left" ? "start" : horizontalAlign === "right" ? "end" : horizontalAlign === "center" ? "center" : undefined;

  return (
    <Box
      display="flex"
      alignItems={alignItems}
      justifyContent={justifyContent}
      className={className}
      style={style}
      {...props}
    >
      {children}
    </Box>
  );
}

/**
 * Grid - Convenience component for grid layouts
 */
export interface GridProps extends BoxProps {
  /** Grid template columns */
  templateColumns?: string;
  /** Grid template rows */
  templateRows?: string;
  /** Grid gap */
  gap?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
}

export function Grid({
  children,
  templateColumns,
  templateRows,
  gap,
  className = "",
  style,
  ...props
}: GridProps) {
  return (
    <Box
      display="grid"
      gridTemplateColumns={templateColumns}
      gridTemplateRows={templateRows}
      gap={gap}
      className={className}
      style={style}
      {...props}
    >
      {children}
    </Box>
  );
}

/**
 * Stack - Vertical or horizontal stack with gap
 */
export interface StackProps extends BoxProps {
  /** Stack direction */
  direction?: "vertical" | "horizontal";
  /** Gap between items */
  gap?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Divider between items */
  divider?: ReactNode;
}

export function Stack({
  children,
  direction = "vertical",
  gap = 4,
  divider,
  className = "",
  style,
  ...props
}: StackProps) {
  const childrenArray = Children.toArray(children);
  const childrenWithDividers = divider
    ? childrenArray.flatMap((child, index) => [
        child,
        index < childrenArray.length - 1 ? (
          <Box key={`divider-${index}`} className="flex-shrink-0">{divider}</Box>
        ) : null,
      ])
    : childrenArray;

  return (
    <Box
      display="flex"
      flexDirection={direction === "vertical" ? "column" : "row"}
      gap={gap}
      className={className}
      style={style}
      {...props}
    >
      {childrenWithDividers}
    </Box>
  );
}

/**
 * Inline - Inline flex container
 */
export interface InlineProps extends BoxProps {
  /** Gap between items */
  gap?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12 | 16;
  /** Align items */
  align?: "start" | "center" | "end" | "stretch" | "baseline";
}

export function Inline({
  children,
  gap = 2,
  align = "center",
  className = "",
  style,
  ...props
}: InlineProps) {
  return (
    <Box
      display="inline-flex"
      alignItems={align}
      gap={gap}
      className={className}
      style={style}
      {...props}
    >
      {children}
    </Box>
  );
}