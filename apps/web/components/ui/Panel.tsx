"use client";

import { createContext, useContext, forwardRef, type HTMLAttributes, type ReactNode } from "react";
import { tv, type VariantProps } from "tailwind-variants";

interface PanelContextValue {
  padding: "none" | "sm" | "md" | "lg";
}

const PanelContext = createContext<PanelContextValue>({ padding: "md" });

const panelStyles = tv({
  base: `
    bg-[var(--color-canvas-inset)]
    border border-[var(--color-border-default)]
    rounded-[var(--radius-lg)]
    transition-colors duration-80 ease-out
  `,
  variants: {
    variant: {
      default: "",
      elevated: "shadow-[var(--shadow-md)]",
      inset: "bg-[var(--color-canvas-subtle)]",
      flush: "border-0 rounded-none shadow-none",
    },
    padding: {
      none: "",
      sm: "p-4 sm:p-5",
      md: "p-5 sm:p-6",
      lg: "p-6 sm:p-8",
    },
  },
  defaultVariants: {
    variant: "default",
    padding: "md",
  },
});

export interface PanelProps extends Omit<HTMLAttributes<HTMLDivElement>, "title">, VariantProps<typeof panelStyles> {
  /** Panel title (renders as header) */
  title?: ReactNode;
  /** Panel subtitle/description */
  subtitle?: ReactNode;
  /** Header action elements */
  headerActions?: ReactNode;
  /** Whether to show a divider after header */
  headerDivider?: boolean;
  /** Footer content */
  footer?: ReactNode;
  /** Footer divider */
  footerDivider?: boolean;
}

export const Panel = forwardRef<HTMLDivElement, PanelProps>(
  function Panel(
    {
      title,
      subtitle,
      headerActions,
      headerDivider = false,
      footer,
      footerDivider = false,
      variant = "default",
      padding = "md",
      className,
      children,
      ...props
    },
    ref
  ) {
    const hasHeader = title !== undefined;
    const contentPadding = padding !== "none" ? "" : "p-0";

    return (
      <PanelContext.Provider value={{ padding: padding || "md" }}>
        <div
          ref={ref}
          className={`${panelStyles({ variant, padding })} ${contentPadding} ${className || ""}`}
          {...props}
        >
          {hasHeader && (
            <header className="flex items-start justify-between gap-4 mb-4">
              <div className="flex-1 min-w-0">
                {title && (
                  <h2 className="text-sm font-semibold text-[var(--color-fg-default)] truncate">{title}</h2>
                )}
                {subtitle && (
                  <p className="text-[11px] text-[var(--color-fg-muted)] mt-0.5 truncate">{subtitle}</p>
                )}
              </div>
              {headerActions && (
                <div className="flex items-center gap-2 shrink-0 ml-4">{headerActions}</div>
              )}
            </header>
          )}

          {hasHeader && headerDivider && (
            <div className="mb-4 border-t border-[var(--color-border-default)]" />
          )}

          <div className={padding === "none" ? "p-0" : ""}>{children}</div>

          {footer && (
            <>
              {footerDivider && (
                <div className="mt-4 border-t border-[var(--color-border-default)]" />
              )}
              <footer className="flex items-center justify-end gap-2 mt-4 pt-4">
                {footer}
              </footer>
            </>
          )}
        </div>
      </PanelContext.Provider>
    );
  }
);
Panel.displayName = "Panel";

/** Panel Section - for dividing panel content into sections */
export interface PanelSectionProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** Section title */
  title?: ReactNode;
  /** Section subtitle */
  subtitle?: ReactNode;
  /** Whether to show section divider before */
  dividerBefore?: boolean;
}

export const PanelSection = forwardRef<HTMLDivElement, PanelSectionProps>(
  function PanelSection({ title, subtitle, dividerBefore = false, className, children, ...props }, ref) {
    const { padding } = useContext(PanelContext);
    const isUnpaddedParent = padding === "none";

    const paddingClasses = isUnpaddedParent ? "px-5 sm:px-6 py-5" : "space-y-4";
    const dividerClasses = dividerBefore
      ? isUnpaddedParent
        ? "border-t border-[var(--color-border-default)]"
        : "mt-4 pt-4 border-t border-[var(--color-border-default)]"
      : "";

    return (
      <div ref={ref} className={`${paddingClasses} ${dividerClasses} ${className || ""}`} {...props}>
        {(title || subtitle) && (
          <div className="flex items-center justify-between gap-4 mb-3">
            <div className="flex-1 min-w-0">
              {title && <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--color-fg-subtle)]">{title}</h3>}
              {subtitle && <p className="text-[11px] text-[var(--color-fg-muted)] mt-0.5">{subtitle}</p>}
            </div>
          </div>
        )}
        {children}
      </div>
    );
  }
);
PanelSection.displayName = "PanelSection";

/** Panel Stack - vertical stack of panels with consistent spacing */
export interface PanelStackProps extends HTMLAttributes<HTMLDivElement> {
  /** Space between panels */
  space?: "sm" | "md" | "lg";
}

export const PanelStack = forwardRef<HTMLDivElement, PanelStackProps>(
  function PanelStack({ space = "md", className, children, ...props }, ref) {
    const spaceMap = { sm: "space-y-3", md: "space-y-4", lg: "space-y-6" };
    return (
      <div ref={ref} className={`${spaceMap[space]} ${className || ""}`} {...props}>
        {children}
      </div>
    );
  }
);
PanelStack.displayName = "PanelStack";

/** Panel Card - compact card variant for dense lists */
export interface PanelCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title" | "onClick"> {
  /** Card title */
  title?: ReactNode;
  /** Card subtitle */
  subtitle?: ReactNode;
  /** Leading icon/avatar */
  leading?: ReactNode;
  /** Trailing action */
  trailing?: ReactNode;
  /** Hoverable (for clickable cards) */
  hoverable?: boolean;
  /** Selected state */
  selected?: boolean;
  /** Click handler - makes card a button */
  onClick?: () => void;
}

export const PanelCard = forwardRef<HTMLDivElement, PanelCardProps>(
  function PanelCard(
    {
      title,
      subtitle,
      leading,
      trailing,
      hoverable = false,
      selected = false,
      className,
      children,
      onClick,
      ...props
    },
    ref
  ) {
    const isButton = !!onClick;

    return (
      <div
        ref={ref}
        role={isButton ? "button" : undefined}
        tabIndex={isButton ? 0 : undefined}
        onClick={onClick}
        onKeyDown={(e) => { if (isButton && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); onClick(); } }}
        className={`
          relative flex items-start gap-3.5 p-4
          bg-[var(--color-canvas-inset)]
          border border-[var(--color-border-default)]
          rounded-[var(--radius-md)]
          transition-colors duration-80 ease-out
          ${selected ? "border-[var(--color-accent-emphasis)] bg-[var(--color-accent-subtle)]" : ""}
          ${hoverable ? "hover:bg-[var(--color-canvas-subtle)] cursor-pointer" : ""}
          ${onClick ? "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]" : ""}
          ${className || ""}
        `}
        {...(!onClick ? props : {})}
      >
        {leading && <div className="flex-shrink-0 mt-0.5">{leading}</div>}
        <div className="flex-1 min-w-0">
          {(title || subtitle) && (
            <div className="flex items-center justify-between gap-2">
              <div className="flex-1 min-w-0">
                {title && <h3 className="text-sm font-medium text-[var(--color-fg-default)] truncate">{title}</h3>}
                {subtitle && <div className="text-[11px] text-[var(--color-fg-muted)] mt-0.5 truncate">{subtitle}</div>}
              </div>
              {trailing && <div className="flex-shrink-0 ml-2">{trailing}</div>}
            </div>
          )}
          {children && <div className="mt-2.5">{children}</div>}
        </div>
      </div>
    );
  }
);
PanelCard.displayName = "PanelCard";

/** Panel Divider - semantic divider within panels */
export interface PanelDividerProps extends HTMLAttributes<HTMLDivElement> {
  /** Optional label in the middle of divider */
  label?: ReactNode;
}

export function PanelDivider({ label, className, ...props }: PanelDividerProps) {
  if (label) {
    return (
      <div className={`flex items-center gap-3 my-4 ${className || ""}`} {...props}>
        <div className="flex-1 border-t border-[var(--color-border-default)]" />
        <span className="px-2.5 text-[10px] font-medium uppercase tracking-wider text-[var(--color-fg-subtle)] bg-[var(--color-canvas-inset)]">
          {label}
        </span>
        <div className="flex-1 border-t border-[var(--color-border-default)]" />
      </div>
    );
  }

  return <div className={`border-t border-[var(--color-border-default)] my-4 ${className || ""}`} {...props} />;
}

/** Panel Header - reusable header pattern for panels */
export interface PanelHeaderProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  /** Header title */
  title: ReactNode;
  /** Header subtitle */
  subtitle?: ReactNode;
  /** Header actions */
  actions?: ReactNode;
  /** Show bottom border */
  divider?: boolean;
}

export function PanelHeader({ title, subtitle, actions, divider = false, className, ...props }: PanelHeaderProps) {
  const { padding } = useContext(PanelContext);
  const isUnpaddedParent = padding === "none";

  const paddingClasses = isUnpaddedParent
    ? "px-5 sm:px-6 pt-4.5 pb-3.5"
    : "mb-4";

  const borderClass = divider
    ? isUnpaddedParent
      ? "border-b border-[var(--color-border-default)]"
      : "pb-3 border-b border-[var(--color-border-default)]"
    : "";

  return (
    <div className={`flex items-start justify-between gap-4 ${paddingClasses} ${borderClass} ${className || ""}`} {...props}>
      <div className="flex-1 min-w-0">
        <h2 className="text-sm font-semibold text-[var(--color-fg-default)] truncate">{title}</h2>
        {subtitle && <p className="text-xs text-[var(--color-fg-muted)] mt-1 truncate">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0 ml-4">{actions}</div>}
    </div>
  );
}

/** Panel Footer - reusable footer pattern for panels */
export interface PanelFooterProps extends HTMLAttributes<HTMLDivElement> {
  /** Show top border */
  divider?: boolean;
  /** Legacy alias for divider */
  dividerBefore?: boolean;
  /** Align content */
  align?: "start" | "center" | "end" | "between";
}

export function PanelFooter({ divider = false, dividerBefore, align = "end", className, children, ...props }: PanelFooterProps) {
  const { padding } = useContext(PanelContext);
  const isUnpaddedParent = padding === "none";
  const showDivider = divider || Boolean(dividerBefore);
  const alignMap = {
    start: "justify-start",
    center: "justify-center",
    end: "justify-end",
    between: "justify-between",
  };

  const paddingClasses = isUnpaddedParent
    ? "px-5 sm:px-6 py-4"
    : "mt-4 pt-3";

  const dividerClasses = showDivider
    ? "border-t border-[var(--color-border-default)]"
    : "";

  return (
    <div
      className={`flex items-center gap-2 ${paddingClasses} ${dividerClasses} ${alignMap[align]} ${className || ""}`}
      {...props}
    >
      {children}
    </div>
  );
}