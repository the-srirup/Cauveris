"use client";

import type { HTMLAttributes } from "react";

export interface ToggleProps extends Omit<HTMLAttributes<HTMLButtonElement>, "onChange"> {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  size?: "sm" | "md" | "lg";
  className?: string;
  "aria-label"?: string;
}

export function Toggle({
  checked,
  onChange,
  disabled = false,
  size = "md",
  className = "",
  "aria-label": ariaLabel,
  ...props
}: ToggleProps) {
  const sizeClasses = {
    sm: "h-4 w-7",
    md: "h-5 w-9",
    lg: "h-6 w-11",
  };

  const thumbSizes = {
    sm: "h-3 w-3",
    md: "h-4 w-4",
    lg: "h-5 w-5",
  };

  const thumbTranslate = {
    sm: { checked: "translate-x-3", unchecked: "translate-x-0.5" },
    md: { checked: "translate-x-4", unchecked: "translate-x-0.5" },
    lg: { checked: "translate-x-5", unchecked: "translate-x-0.5" },
  };

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className={`
        relative inline-flex items-center flex-shrink-0 cursor-pointer rounded-full border border-transparent
        transition-colors duration-100 ease-out
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
        ${disabled ? "opacity-50 cursor-not-allowed" : ""}
        ${checked ? "bg-[var(--color-accent-emphasis)]" : "bg-[var(--color-canvas-muted)] hover:bg-[var(--color-border-default)]"}
        ${sizeClasses[size]} ${className}
      `}
      {...props}
    >
      <span
        className={`
          pointer-events-none inline-block rounded-full bg-white shadow-sm
          transform transition-transform duration-100 ease-out
          ${thumbSizes[size]}
          ${checked ? thumbTranslate[size].checked : thumbTranslate[size].unchecked}
        `}
        aria-hidden="true"
      />
    </button>
  );
}
