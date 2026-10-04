"use client";

import { useState, useRef, useEffect, type ReactNode, forwardRef, isValidElement, cloneElement, Children } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const tooltipStyles = tv({
  base: `
    absolute z-50 px-2.5 py-1.5 text-[11px] font-medium text-[var(--color-text-primary)]
    rounded-lg shadow-lg pointer-events-none
    animate-fade-in
    whitespace-nowrap
  `,
  variants: {
    tone: {
      default: "bg-[var(--color-surface)]/95 text-[var(--color-text-primary)] border border-[var(--color-border)] backdrop-blur-sm",
      primary: "bg-[var(--color-brand-primary)]/90 text-[var(--color-text-primary)] border border-[var(--color-brand-primary)]/30",
      success: "bg-[var(--color-brand-success)]/90 text-[var(--color-text-primary)] border border-[var(--color-brand-success)]/30",
      danger: "bg-[var(--color-brand-danger)]/90 text-[var(--color-text-primary)] border border-[var(--color-brand-danger)]/30",
      muted: "bg-[var(--color-surface)] text-[var(--color-text-muted)] border border-[var(--color-border)]",
    },
    size: {
      sm: "px-2 py-1 text-[10px]",
      md: "px-2.5 py-1.5 text-[11px]",
      lg: "px-3 py-2 text-sm",
    },
  },
  defaultVariants: {
    tone: "default",
    size: "md",
  },
});

const arrowStyles = tv({
  base: `
    absolute w-2 h-2 rotate-45
    pointer-events-none
  `,
  variants: {
    tone: {
      default: "bg-[var(--color-surface)]/95 border-l border-t border-[var(--color-border)]",
      primary: "bg-[var(--color-brand-primary)]/90",
      success: "bg-[var(--color-brand-success)]/90",
      danger: "bg-[var(--color-brand-danger)]/90",
      muted: "bg-[var(--color-surface)]",
    },
  },
  defaultVariants: {
    tone: "default",
  },
});

export interface TooltipProps extends VariantProps<typeof tooltipStyles> {
  content: ReactNode;
  children: ReactNode;
  position?: "top" | "bottom" | "left" | "right";
  offset?: number;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  delay?: number;
  className?: string;
}

export const Tooltip = forwardRef<HTMLDivElement, TooltipProps>(
  (
    {
      content,
      children,
      position = "top",
      offset = 8,
      open: controlledOpen,
      onOpenChange,
      delay = 200,
      tone,
      size,
      className,
      ...props
    },
    ref
  ) => {
    const [uncontrolledOpen, setUncontrolledOpen] = useState<boolean>(false);
    const [arrowPosition, setArrowPosition] = useState({ x: 0, y: 0 });
    const tooltipRef = useRef<HTMLDivElement>(null);
    const childRef = useRef<HTMLElement>(null);
    const timeoutRef = useRef<NodeJS.Timeout | null>(null);
    const tooltipId = useRef(`tooltip-${Math.random().toString(36).substr(2, 9)}`);

    const isControlled = controlledOpen !== undefined;
    const open = isControlled ? controlledOpen : uncontrolledOpen;

    const setOpen = (value: boolean) => {
      if (!isControlled) setUncontrolledOpen(value);
      onOpenChange?.(value);
    };

    const showTooltip = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setOpen(true), delay);
    };

    const hideTooltip = () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      setOpen(false);
    };

    // Update position when open
    useEffect(() => {
      if (!open || !childRef.current || !tooltipRef.current) return;

      const childRect = childRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportWidth = window.innerWidth;
      const viewportHeight = window.innerHeight;

      let top = 0;
      let left = 0;
      let arrowX = 0;
      let arrowY = 0;

      switch (position) {
        case "top":
          top = childRect.top - tooltipRect.height - offset;
          left = childRect.left + childRect.width / 2 - tooltipRect.width / 2;
          arrowX = tooltipRect.width / 2 - 4;
          arrowY = tooltipRect.height - 4;
          // Flip to bottom if no space
          if (top < 8) {
            top = childRect.bottom + offset;
            arrowY = 4;
          }
          break;
        case "bottom":
          top = childRect.bottom + offset;
          left = childRect.left + childRect.width / 2 - tooltipRect.width / 2;
          arrowX = tooltipRect.width / 2 - 4;
          arrowY = 4;
          // Flip to top if no space
          if (top + tooltipRect.height > viewportHeight - 8) {
            top = childRect.top - tooltipRect.height - offset;
            arrowY = tooltipRect.height - 4;
          }
          break;
        case "left":
          top = childRect.top + childRect.height / 2 - tooltipRect.height / 2;
          left = childRect.left - tooltipRect.width - offset;
          arrowX = tooltipRect.width - 4;
          arrowY = tooltipRect.height / 2 - 4;
          // Flip to right if no space
          if (left < 8) {
            left = childRect.right + offset;
            arrowX = 4;
          }
          break;
        case "right":
          top = childRect.top + childRect.height / 2 - tooltipRect.height / 2;
          left = childRect.right + offset;
          arrowX = 4;
          arrowY = tooltipRect.height / 2 - 4;
          // Flip to left if no space
          if (left + tooltipRect.width > viewportWidth - 8) {
            left = childRect.left - tooltipRect.width - offset;
            arrowX = tooltipRect.width - 4;
          }
          break;
      }

      // Clamp to viewport
      left = Math.max(8, Math.min(left, viewportWidth - tooltipRect.width - 8));
      top = Math.max(8, Math.min(top, viewportHeight - tooltipRect.height - 8));

      setArrowPosition({ x: arrowX, y: arrowY });
      tooltipRef.current.style.top = `${top}px`;
      tooltipRef.current.style.left = `${left}px`;
    }, [open, position, offset]);

    // Cleanup
    useEffect(() => {
      return () => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
      };
    }, []);

    // Wrap child to attach ref and events
    const childWithRef = typeof children === "function" ? children : () => children;
    const childElement = childWithRef();

    // We need to clone the child to attach ref and events
    const enhancedChild = isValidElement(childElement)
      ? cloneElement(childElement as React.ReactElement<any>, {
          ref: childRef,
          onMouseEnter: showTooltip,
          onMouseLeave: hideTooltip,
          onFocus: showTooltip,
          onBlur: hideTooltip,
          'aria-describedby': open ? tooltipId.current : undefined,
          ...(childElement.props as any),
        })
      : childElement;

    return (
      <div ref={ref} className="inline-block relative" {...props}>
        {enhancedChild}
        {open && (
          <div
            ref={tooltipRef}
            id={tooltipId.current}
            className={tooltipStyles({ tone, size, className })}
            role="tooltip"
          >
            {content}
            <div
              className={arrowStyles({ tone })}
              style={{
                left: `${arrowPosition.x}px`,
                top: `${arrowPosition.y}px`,
              }}
            />
          </div>
        )}
      </div>
    );
  }
);

Tooltip.displayName = "Tooltip";

/* -------------------------------------------------------------------------- */
/* Tooltip Trigger - Convenience wrapper for common patterns                  */
/* -------------------------------------------------------------------------- */

export interface TooltipTriggerProps extends Omit<TooltipProps, "children"> {
  children: ReactNode;
  "aria-label"?: string;
}

export function TooltipTrigger({ children, "aria-label": ariaLabel, ...props }: TooltipTriggerProps) {
  const child = Children.only(children);
  return (
    <Tooltip {...props}>
      {child}
    </Tooltip>
  );
}