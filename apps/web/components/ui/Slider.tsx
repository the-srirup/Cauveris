"use client";

import { forwardRef, type HTMLAttributes, type ReactNode, useId, useRef, useState, useEffect, useCallback } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const sliderStyles = tv({
  base: `
    relative w-full select-none
    [&_input]:appearance-none [&_input]:w-full [&_input]:h-full [&_input]:bg-transparent [&_input]:cursor-pointer
    [&_input]:focus-visible:outline-none [&_input]:focus-visible:ring-0
  `,
  variants: {
    size: {
      sm: "h-1",
      md: "h-1.5",
      lg: "h-2",
    },
    variant: {
      default: `
        [&_track]:bg-[var(--color-border-default)]
        [&_fill]:bg-[var(--color-accent-emphasis)]
        [&_thumb]:bg-[var(--color-accent-fg)] [&_thumb]:border-[var(--color-accent-emphasis)]
        [&_input]:hover_[&_thumb]:bg-[var(--color-accent-fg)]/90
        [&_input]:active_[&_thumb]:bg-[var(--color-accent-emphasis)]
      `,
      success: `
        [&_track]:bg-[var(--color-success-muted)]
        [&_fill]:bg-[var(--color-success-emphasis)]
        [&_thumb]:bg-[var(--color-success-fg)] [&_thumb]:border-[var(--color-success-emphasis)]
        [&_input]:hover_[&_thumb]:bg-[var(--color-success-fg)]/90
        [&_input]:active_[&_thumb]:bg-[var(--color-success-emphasis)]
      `,
      danger: `
        [&_track]:bg-[var(--color-danger-muted)]
        [&_fill]:bg-[var(--color-danger-emphasis)]
        [&_thumb]:bg-[var(--color-danger-fg)] [&_thumb]:border-[var(--color-danger-emphasis)]
        [&_input]:hover_[&_thumb]:bg-[var(--color-danger-fg)]/90
        [&_input]:active_[&_thumb]:bg-[var(--color-danger-emphasis)]
      `,
      muted: `
        [&_track]:bg-[var(--color-border-muted)]
        [&_fill]:bg-[var(--color-fg-muted)]
        [&_thumb]:bg-[var(--color-fg-muted)] [&_thumb]:border-[var(--color-fg-muted)]
        [&_input]:hover_[&_thumb]:bg-[var(--color-fg-subtle)]
        [&_input]:active_[&_thumb]:bg-[var(--color-fg-muted)]
      `,
    },
  },
  defaultVariants: {
    size: "md",
    variant: "default",
  },
});

// Track, Fill, Thumb are styled via CSS custom properties and pseudo-elements
// We use data attributes for styling

interface SliderProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** Current value */
  value: number;
  /** Minimum value */
  min?: number;
  /** Maximum value */
  max?: number;
  /** Step increment */
  step?: number;
  /** Value change callback */
  onValueChange?: (value: number) => void;
  /** Show value label */
  showValue?: boolean;
  /** Value label formatter */
  valueFormatter?: (value: number) => string;
  /** Slider size */
  size?: "sm" | "md" | "lg";
  /** Visual variant */
  variant?: "default" | "success" | "danger" | "muted";
  /** Disabled state */
  disabled?: boolean;
  /** Label for accessibility */
  "aria-label"?: string;
  /** Labelledby for accessibility */
  "aria-labelledby"?: string;
}

export const Slider = forwardRef<HTMLDivElement, SliderProps>(
  function Slider(
    {
      value,
      min = 0,
      max = 100,
      step = 1,
      onValueChange,
      showValue = false,
      valueFormatter,
      size = "md",
      variant = "default",
      disabled = false,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
      ...props
    },
    ref
  ) {
    const sliderId = useId();
    const trackRef = useRef<HTMLDivElement>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [focused, setFocused] = useState(false);

    // Clamp value to min/max/step
    const clampedValue = useCallback(
      (v: number) => {
        const stepped = Math.round((v - min) / step) * step + min;
        return Math.max(min, Math.min(max, stepped));
      },
      [min, max, step]
    );

    const percentage = ((clampedValue(value) - min) / (max - min)) * 100;

    const handleChange = useCallback(
      (clientX: number) => {
        if (disabled || !trackRef.current) return;
        const rect = trackRef.current.getBoundingClientRect();
        const relativeX = clientX - rect.left;
        const newPercentage = Math.max(0, Math.min(100, (relativeX / rect.width) * 100));
        const newValue = min + (newPercentage / 100) * (max - min);
        const clamped = clampedValue(newValue);
        onValueChange?.(clamped);
      },
      [disabled, min, max, onValueChange, clampedValue]
    );

    const handleMouseDown = useCallback(
      (e: React.MouseEvent) => {
        if (disabled) return;
        setIsDragging(true);
        handleChange(e.clientX);
        e.preventDefault();
      },
      [disabled, handleChange]
    );

    const handleTouchStart = useCallback(
      (e: React.TouchEvent) => {
        if (disabled) return;
        setIsDragging(true);
        handleChange(e.touches[0].clientX);
      },
      [disabled, handleChange]
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (disabled) return;
        let newValue = clampedValue(value);
        const stepValue = step;
        switch (e.key) {
          case "ArrowRight":
          case "ArrowUp":
            e.preventDefault();
            newValue = clampedValue(value + stepValue);
            break;
          case "ArrowLeft":
          case "ArrowDown":
            e.preventDefault();
            newValue = clampedValue(value - stepValue);
            break;
          case "Home":
            e.preventDefault();
            newValue = min;
            break;
          case "End":
            e.preventDefault();
            newValue = max;
            break;
          case "PageUp":
            e.preventDefault();
            newValue = clampedValue(value + stepValue * 10);
            break;
          case "PageDown":
            e.preventDefault();
            newValue = clampedValue(value - stepValue * 10);
            break;
          default:
            return;
        }
        onValueChange?.(newValue);
      },
      [disabled, value, min, max, step, onValueChange, clampedValue]
    );

    // Global mouse/touch move/up handlers
    useEffect(() => {
      if (!isDragging) return;

      const handleMove = (e: MouseEvent | TouchEvent) => {
        const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
        handleChange(clientX);
      };

      const handleUp = () => {
        setIsDragging(false);
      };

      window.addEventListener("mousemove", handleMove);
      window.addEventListener("touchmove", handleMove, { passive: true });
      window.addEventListener("mouseup", handleUp);
      window.addEventListener("touchend", handleUp);

      return () => {
        window.removeEventListener("mousemove", handleMove);
        window.removeEventListener("touchmove", handleMove);
        window.removeEventListener("mouseup", handleUp);
        window.removeEventListener("touchend", handleUp);
      };
    }, [isDragging, handleChange]);

    const formattedValue = valueFormatter ? valueFormatter(value) : `${value}`;

    return (
      <div
        ref={ref}
        className={`${sliderStyles({ size, variant })} ${className || ""}`}
        role="slider"
        aria-valuenow={clampedValue(value)}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-disabled={disabled}
        aria-label={ariaLabel}
        aria-labelledby={ariaLabelledby}
        aria-orientation="horizontal"
        tabIndex={disabled ? -1 : 0}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={handleKeyDown}
        {...props}
      >
        <div
          ref={trackRef}
          className="relative w-full h-full rounded-full overflow-hidden bg-transparent"
          data-track
          onMouseDown={handleMouseDown}
          onTouchStart={handleTouchStart}
        >
          {/* Track background */}
          <div
            className="absolute inset-0 h-full rounded-full"
            data-track
            style={{ background: "var(--slider-track-bg, var(--color-border-default))" }}
          />

          {/* Fill progress */}
          <div
            className="absolute left-0 top-0 h-full rounded-full transition-[width] duration-80 ease-out"
            data-fill
            style={{
              width: `${percentage}%`,
              background: "var(--slider-fill-bg, var(--color-accent-emphasis))",
            }}
          />

          {/* Thumb: Engineering Precision Scrubber */}
          <div
            className={`
              absolute top-1/2 -translate-y-1/2 -translate-x-1/2
              rounded-[2px] border border-[var(--color-border-default)]
              transition-[left,box-shadow] duration-75 ease-out
              ${focused || isDragging ? "ring-2 ring-[var(--color-accent)] ring-offset-1 ring-offset-[var(--color-canvas)] shadow-sm" : "shadow-none"}
              ${disabled ? "opacity-50 pointer-events-none" : "hover:border-[var(--color-fg-muted)]"}
            `}
            data-thumb
            style={{
              left: `${percentage}%`,
              width: size === "sm" ? "8px" : size === "md" ? "10px" : "12px",
              height: size === "sm" ? "16px" : size === "md" ? "18px" : "20px",
              background: "var(--slider-thumb-bg, var(--color-canvas-elevated, var(--color-canvas)))",
              borderColor: "var(--slider-thumb-border, var(--color-border-default))",
            }}
          />
        </div>

        {/* Value Label */}
        {showValue && (
          <div
            className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-mono text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)] pointer-events-none"
            aria-hidden="true"
            style={{ left: `${percentage}%` }}
          >
            {formattedValue}
          </div>
        )}
      </div>
    );
  }
);
Slider.displayName = "Slider";

/** Range Slider for dual-handle ranges */
export interface RangeSliderProps extends Omit<HTMLAttributes<HTMLDivElement>, "onChange"> {
  /** Current range value [min, max] */
  value: [number, number];
  /** Minimum value */
  min?: number;
  /** Maximum value */
  max?: number;
  /** Step increment */
  step?: number;
  /** Value change callback */
  onValueChange?: (value: [number, number]) => void;
  /** Show value labels */
  showValue?: boolean;
  /** Value label formatter */
  valueFormatter?: (value: number) => string;
  /** Slider size */
  size?: "sm" | "md" | "lg";
  /** Visual variant */
  variant?: "default" | "success" | "danger" | "muted";
  /** Disabled state */
  disabled?: boolean;
  /** Minimum distance between handles */
  minDistance?: number;
  /** Label for accessibility */
  "aria-label"?: string;
  /** Labelledby for accessibility */
  "aria-labelledby"?: string;
}

export const RangeSlider = forwardRef<HTMLDivElement, RangeSliderProps>(
  function RangeSlider(
    {
      value,
      min = 0,
      max = 100,
      step = 1,
      onValueChange,
      showValue = false,
      valueFormatter,
      size = "md",
      variant = "default",
      disabled = false,
      minDistance = 0,
      className,
      "aria-label": ariaLabel,
      "aria-labelledby": ariaLabelledby,
      ...props
    },
    ref
  ) {
    const sliderId = useId();
    const trackRef = useRef<HTMLDivElement>(null);
    const [activeHandle, setActiveHandle] = useState<0 | 1 | null>(null);
    const [focused, setFocused] = useState<0 | 1 | false>(false);

    const clampedValue = useCallback(
      (v: number) => {
        const stepped = Math.round((v - min) / step) * step + min;
        return Math.max(min, Math.min(max, stepped));
      },
      [min, max, step]
    );

    const [valMin, valMax] = value;
    const pctMin = ((clampedValue(valMin) - min) / (max - min)) * 100;
    const pctMax = ((clampedValue(valMax) - min) / (max - min)) * 100;

    const handleChange = useCallback(
      (clientX: number, handle: 0 | 1) => {
        if (disabled || !trackRef.current) return;
        const rect = trackRef.current.getBoundingClientRect();
        const relativeX = clientX - rect.left;
        const newPercentage = Math.max(0, Math.min(100, (relativeX / rect.width) * 100));
        const newValue = min + (newPercentage / 100) * (max - min);
        const clamped = clampedValue(newValue);

        if (handle === 0) {
          // Ensure min handle doesn't cross max handle minus minDistance
          const maxAllowed = clampedValue(valMax - minDistance);
          onValueChange?.([Math.min(clamped, maxAllowed), valMax]);
        } else {
          // Ensure max handle doesn't cross min handle plus minDistance
          const minAllowed = clampedValue(valMin + minDistance);
          onValueChange?.([valMin, Math.max(clamped, minAllowed)]);
        }
      },
      [disabled, min, max, valMin, valMax, minDistance, onValueChange, clampedValue]
    );

    const handleMouseDown = useCallback(
      (e: React.MouseEvent, handle: 0 | 1) => {
        if (disabled) return;
        setActiveHandle(handle);
        handleChange(e.clientX, handle);
        e.preventDefault();
      },
      [disabled, handleChange]
    );

    const handleTouchStart = useCallback(
      (e: React.TouchEvent, handle: 0 | 1) => {
        if (disabled) return;
        setActiveHandle(handle);
        handleChange(e.touches[0].clientX, handle);
      },
      [disabled, handleChange]
    );

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent, handle: 0 | 1) => {
        if (disabled) return;
        const currentVal = handle === 0 ? valMin : valMax;
        const otherVal = handle === 0 ? valMax : valMin;
        let newValue = clampedValue(currentVal);
        const stepValue = step;

        switch (e.key) {
          case "ArrowRight":
          case "ArrowUp":
            e.preventDefault();
            newValue = clampedValue(currentVal + stepValue);
            break;
          case "ArrowLeft":
          case "ArrowDown":
            e.preventDefault();
            newValue = clampedValue(currentVal - stepValue);
            break;
          case "Home":
            e.preventDefault();
            newValue = min;
            break;
          case "End":
            e.preventDefault();
            newValue = max;
            break;
          case "PageUp":
            e.preventDefault();
            newValue = clampedValue(currentVal + stepValue * 10);
            break;
          case "PageDown":
            e.preventDefault();
            newValue = clampedValue(currentVal - stepValue * 10);
            break;
          default:
            return;
        }

        // Check minDistance constraint
        if (handle === 0 && newValue > otherVal - minDistance) return;
        if (handle === 1 && newValue < otherVal + minDistance) return;

        onValueChange?.(handle === 0 ? [newValue, otherVal] : [otherVal, newValue]);
      },
      [disabled, valMin, valMax, min, max, step, minDistance, onValueChange, clampedValue]
    );

    useEffect(() => {
      if (activeHandle === null) return;

      const handleMove = (e: MouseEvent | TouchEvent) => {
        const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
        handleChange(clientX, activeHandle);
      };

      const handleUp = () => {
        setActiveHandle(null);
      };

      window.addEventListener("mousemove", handleMove);
      window.addEventListener("touchmove", handleMove, { passive: true });
      window.addEventListener("mouseup", handleUp);
      window.addEventListener("touchend", handleUp);

      return () => {
        window.removeEventListener("mousemove", handleMove);
        window.removeEventListener("touchmove", handleMove);
        window.removeEventListener("mouseup", handleUp);
        window.removeEventListener("touchend", handleUp);
      };
    }, [activeHandle, handleChange]);

    const formatVal = (v: number) => (valueFormatter ? valueFormatter(v) : `${v}`);

    return (
      <div
        ref={ref}
        className={`${sliderStyles({ size, variant })} ${className || ""}`}
        {...props}
      >
        <div
          ref={trackRef}
          className="relative w-full h-full rounded-full overflow-hidden bg-transparent"
          data-track
        >
          {/* Track background */}
          <div
            className="absolute inset-0 h-full rounded-full"
            data-track
            style={{ background: "var(--slider-track-bg, var(--color-border-default))" }}
          />

          {/* Range fill */}
          <div
            className="absolute top-0 h-full rounded-full transition-[left,width] duration-80 ease-out"
            data-fill
            style={{
              left: `${pctMin}%`,
              width: `${pctMax - pctMin}%`,
              background: "var(--slider-fill-bg, var(--color-accent-emphasis))",
            }}
          />

          {/* Min Thumb */}
          <button
            type="button"
            className={`
              absolute top-1/2 -translate-y-1/2 -translate-x-1/2
              rounded-full border-2
              transition-transform duration-80 ease-out, box-shadow duration-80 ease-out
              ${focused === 0 || activeHandle === 0 ? "scale-150 shadow-[0_0_0_3px_var(--color-accent-muted)]" : "scale-100"}
              ${disabled ? "opacity-50 pointer-events-none" : ""}
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
            `}
            data-thumb
            data-handle="min"
            style={{
              left: `${pctMin}%`,
              width: size === "sm" ? "12px" : size === "md" ? "14px" : "16px",
              height: size === "sm" ? "12px" : size === "md" ? "14px" : "16px",
              background: "var(--slider-thumb-bg, var(--color-accent-fg))",
              borderColor: "var(--slider-thumb-border, var(--color-accent-emphasis))",
            }}
            onMouseDown={(e) => handleMouseDown(e, 0)}
            onTouchStart={(e) => handleTouchStart(e, 0)}
            onFocus={() => setFocused(0)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => handleKeyDown(e, 0)}
            tabIndex={disabled ? -1 : 0}
            role="slider"
            aria-valuenow={clampedValue(valMin)}
            aria-valuemin={min}
            aria-valuemax={clampedValue(valMax - minDistance)}
            aria-disabled={disabled}
            aria-label={ariaLabel ? `${ariaLabel} (minimum)` : "Minimum"}
            aria-controls={sliderId}
          />

          {/* Max Thumb */}
          <button
            type="button"
            className={`
              absolute top-1/2 -translate-y-1/2 -translate-x-1/2
              rounded-full border-2
              transition-transform duration-80 ease-out, box-shadow duration-80 ease-out
              ${focused === 1 || activeHandle === 1 ? "scale-150 shadow-[0_0_0_3px_var(--color-accent-muted)]" : "scale-100"}
              ${disabled ? "opacity-50 pointer-events-none" : ""}
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
            `}
            data-thumb
            data-handle="max"
            style={{
              left: `${pctMax}%`,
              width: size === "sm" ? "12px" : size === "md" ? "14px" : "16px",
              height: size === "sm" ? "12px" : size === "md" ? "14px" : "16px",
              background: "var(--slider-thumb-bg, var(--color-accent-fg))",
              borderColor: "var(--slider-thumb-border, var(--color-accent-emphasis))",
            }}
            onMouseDown={(e) => handleMouseDown(e, 1)}
            onTouchStart={(e) => handleTouchStart(e, 1)}
            onFocus={() => setFocused(1)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => handleKeyDown(e, 1)}
            tabIndex={disabled ? -1 : 0}
            role="slider"
            aria-valuenow={clampedValue(valMax)}
            aria-valuemin={clampedValue(valMin + minDistance)}
            aria-valuemax={max}
            aria-disabled={disabled}
            aria-label={ariaLabel ? `${ariaLabel} (maximum)` : "Maximum"}
            aria-controls={sliderId}
          />
        </div>

        {/* Value Labels */}
        {showValue && (
          <>
            <div
              className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-mono text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)] pointer-events-none"
              aria-hidden="true"
              style={{ left: `${pctMin}%` }}
            >
              {formatVal(valMin)}
            </div>
            <div
              className="absolute -top-8 left-1/2 -translate-x-1/2 whitespace-nowrap text-xs font-mono text-[var(--color-fg-muted)] bg-[var(--color-canvas-subtle)] px-1.5 py-0.5 rounded-[var(--radius-sm)] pointer-events-none"
              aria-hidden="true"
              style={{ left: `${pctMax}%` }}
            >
              {formatVal(valMax)}
            </div>
          </>
        )}
      </div>
    );
  }
);
RangeSlider.displayName = "RangeSlider";

/** Slider with labeled marks for discrete values */
export interface MarkedSliderProps extends Omit<SliderProps, "valueFormatter"> {
  /** Marks at specific values */
  marks?: Array<{ value: number; label?: string }>;
  /** Show mark labels */
  showMarkLabels?: boolean;
}

export function MarkedSlider({
  marks = [],
  showMarkLabels = false,
  min = 0,
  max = 100,
  size = "md",
  variant = "default",
  className,
  children,
  ...props
}: MarkedSliderProps) {
  const [trackWidth, setTrackWidth] = useState(0);

  useEffect(() => {
    const updateWidth = () => {
      // We can't easily get the width without a ref, so we'll use a workaround
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  const markPositions = marks.map((mark) => ({
    ...mark,
    percentage: ((mark.value - min) / (max - min)) * 100,
  }));

  return (
    <div className={`relative ${className || ""}`}>
      <Slider size={size} variant={variant} {...props} />

      {marks.length > 0 && (
        <div
          className="absolute bottom-full left-0 right-0 mb-2 h-[4px] pointer-events-none"
          style={{ marginLeft: size === "sm" ? "6px" : size === "md" ? "7px" : "8px", marginRight: size === "sm" ? "6px" : size === "md" ? "7px" : "8px" }}
        >
          {markPositions.map((mark) => (
            <div
              key={mark.value}
              className="absolute top-0 w-[2px] h-[4px] -translate-x-1/2"
              style={{
                left: `${mark.percentage}%`,
                background: "var(--color-border-default)",
              }}
            />
          ))}
        </div>
      )}

      {showMarkLabels && marks.length > 0 && (
        <div className="flex justify-between mt-2 text-[10px] text-[var(--color-fg-subtle)] font-mono">
          {markPositions.map((mark) => (
            <span key={mark.value} className="whitespace-nowrap">
              {mark.label ?? mark.value}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}