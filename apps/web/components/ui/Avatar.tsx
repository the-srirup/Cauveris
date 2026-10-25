"use client";

import type { ReactNode } from "react";

export interface AvatarProps {
  /** Image source */
  src?: string;
  /** Fallback text (initials, name) */
  fallback?: string;
  /** Alt text for image */
  alt?: string;
  /** Size variant */
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Shape */
  shape?: "circle" | "square";
  /** Additional class names */
  className?: string;
  /** Status indicator */
  status?: "online" | "offline" | "busy" | "away";
  /** Status position */
  statusPosition?: "bottom-right" | "top-right" | "bottom-left" | "top-left";
}

const sizeClasses = {
  xs: "h-5 w-5 text-[10px]",
  sm: "h-7 w-7 text-xs",
  md: "h-8 w-8 text-sm",
  lg: "h-10 w-10 text-base",
  xl: "h-12 w-12 text-lg",
};

const statusSizes = {
  xs: "h-1.5 w-1.5",
  sm: "h-2 w-2",
  md: "h-2 w-2",
  lg: "h-2.5 w-2.5",
  xl: "h-3 w-3",
};

const statusPositions = {
  "bottom-right": "bottom-0 right-0",
  "top-right": "top-0 right-0",
  "bottom-left": "bottom-0 left-0",
  "top-left": "top-0 left-0",
};

const statusColors = {
  online: "bg-[var(--color-success-emphasis)]",
  offline: "bg-[var(--color-fg-subtle)]",
  busy: "bg-[var(--color-danger-emphasis)]",
  away: "bg-[var(--color-attention-emphasis)]",
};

export function Avatar({
  src,
  fallback,
  alt = "",
  size = "md",
  shape = "circle",
  className = "",
  status,
  statusPosition = "bottom-right",
}: AvatarProps) {
  const isCircle = shape === "circle";
  const borderRadius = isCircle ? "rounded-full" : "rounded-[var(--radius-md)]";

  // Generate color from fallback string for consistent avatar colors
  const getColorFromString = (str: string) => {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hue = hash % 360;
    return `hsl(${hue}, 65%, 45%)`;
  };

  const bgColor = fallback ? getColorFromString(fallback) : "var(--color-accent-muted)";

  const initials = fallback
    ? fallback
        .split(" ")
        .map((part) => part[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "?";

  return (
    <div className={`relative inline-flex ${className}`}>
      <div
        className={`inline-flex items-center justify-center select-none overflow-hidden bg-[${bgColor}] text-[var(--color-fg-on-emphasis)] font-medium ${sizeClasses[size]} ${borderRadius}`}
        aria-label={alt || fallback}
      >
        {src ? (
          <img
            src={src}
            alt={alt}
            className="h-full w-full object-cover"
            loading="lazy"
          />
        ) : (
          <span aria-hidden="true">{initials}</span>
        )}
      </div>
      {status && (
        <span
          className={`
            absolute border-2 border-[var(--color-canvas)]
            ${statusSizes[size]}
            ${statusColors[status]}
            ${statusPositions[statusPosition]}
            rounded-full
          `}
          aria-label={`Status: ${status}`}
        />
      )}
    </div>
  );
}

export interface AvatarStackProps {
  /** Array of avatar sources */
  srcs: string[];
  /** Maximum number of avatars to show */
  max?: number;
  /** Size variant */
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** Additional class names */
  className?: string;
  /** Total count if more than max (shows as +N) */
  totalCount?: number;
}

export function AvatarStack({ srcs, max = 5, size = "md", className = "", totalCount }: AvatarStackProps) {
  const visibleAvatars = srcs.slice(0, max);
  const remainingCount = totalCount || srcs.length - max;

  return (
    <div className={`inline-flex -space-x-2 ${className}`} aria-label={`${srcs.length} avatars`}>
      {visibleAvatars.map((src, index) => (
        <Avatar key={src} src={src} size={size} className={index === 0 ? "" : "ring-2 ring-[var(--color-canvas)]"} />
      ))}
      {remainingCount > 0 && (
        <div
          className={`
            inline-flex items-center justify-center
            bg-[var(--color-canvas-subtle)] text-[var(--color-fg-muted)]
            border-2 border-[var(--color-canvas)]
            font-medium ${sizeClasses[size]} rounded-full
          `}
          aria-label={`${remainingCount} more`}
        >
          +{remainingCount}
        </div>
      )}
    </div>
  );
}