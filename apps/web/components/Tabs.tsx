"use client";

import { useState, useRef, useEffect, type ReactNode, forwardRef, createContext, useContext } from "react";
import { tv, type VariantProps } from "tailwind-variants";

const tabsListStyles = tv({
  base: `
    flex gap-1 p-1 bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)]
    aria-orientation-horizontal
  `,
  variants: {
    variant: {
      line: "",
      enclosed: "",
      soft: "",
    },
  },
});

const tabTriggerStyles = tv({
  base: `
    relative flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium
    rounded-lg transition-all duration-150 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-background
    disabled:opacity-50 disabled:cursor-not-allowed
    data-[state=active]:font-semibold
  `,
  variants: {
    variant: {
      line: `
        text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]
        data-[state=active]:text-[var(--color-accent)]
      `,
      enclosed: `
        text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface)]
        data-[state=active]:text-[var(--color-text-primary)] data-[state=active]:bg-[var(--theme-background)] data-[state=active]:shadow-sm
      `,
      soft: `
        text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]
        data-[state=active]:text-[var(--color-accent)] data-[state=active]:bg-[var(--color-accent)]/10
      `,
    },
    size: {
      sm: "px-2.5 py-1 text-xs",
      md: "px-3 py-1.5 text-sm",
      lg: "px-4 py-2 text-base",
    },
  },
  defaultVariants: {
    variant: "line",
    size: "md",
  },
});

const tabContentStyles = tv({
  base: `
    mt-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2
  `,
  variants: {
    animated: {
      true: "animate-fade-in",
      false: "",
    },
  },
  defaultVariants: {
    animated: true,
  },
});

/* -------------------------------------------------------------------------- */
/* Context                                                                    */
/* -------------------------------------------------------------------------- */

interface TabsContextValue {
  value: string;
  onValueChange: (value: string) => void;
  variant: "line" | "enclosed" | "soft";
  size: "sm" | "md" | "lg";
  orientation: "horizontal" | "vertical";
  activationMode: "automatic" | "manual";
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("Tabs components must be used within Tabs.Root");
  }
  return context;
}

/* -------------------------------------------------------------------------- */
/* Root                                                                       */
/* -------------------------------------------------------------------------- */

interface TabsRootProps {
  value: string;
  onValueChange: (value: string) => void;
  defaultValue?: string;
  variant?: "line" | "enclosed" | "soft";
  size?: "sm" | "md" | "lg";
  orientation?: "horizontal" | "vertical";
  activationMode?: "automatic" | "manual";
  children: ReactNode;
  className?: string;
}

export const TabsRoot = forwardRef<HTMLDivElement, TabsRootProps>(
  (
    {
      value,
      onValueChange,
      defaultValue,
      variant = "line",
      size = "md",
      orientation = "horizontal",
      activationMode = "automatic",
      children,
      className,
    },
    ref
  ) => {
    const [internalValue, setInternalValue] = useState(defaultValue || "");
    const controlled = value !== undefined;
    const currentValue = controlled ? value : internalValue;

    const handleValueChange = (newValue: string) => {
      if (!controlled) setInternalValue(newValue);
      onValueChange(newValue);
    };

    return (
      <TabsContext.Provider
        value={{
          value: currentValue,
          onValueChange: handleValueChange,
          variant,
          size,
          orientation,
          activationMode,
        }}
      >
        <div ref={ref} className={className}>
          {children}
        </div>
      </TabsContext.Provider>
    );
  }
);

TabsRoot.displayName = "TabsRoot";

/* -------------------------------------------------------------------------- */
/* List                                                                       */
/* -------------------------------------------------------------------------- */

interface TabsListProps {
  children: ReactNode;
  className?: string;
  "aria-label"?: string;
  "aria-orientation"?: "horizontal" | "vertical";
}

export const TabsList = forwardRef<HTMLDivElement, TabsListProps>(
  ({ children, className, "aria-label": ariaLabel, "aria-orientation": ariaOrientation, ...props }, ref) => {
    const { variant, size, orientation } = useTabsContext();
    return (
      <div
        ref={ref}
        role="tablist"
        aria-label={ariaLabel}
        aria-orientation={ariaOrientation || orientation}
        className={tabsListStyles({ variant, className })}
        {...props}
      >
        {children}
      </div>
    );
  }
);

TabsList.displayName = "TabsList";

/* -------------------------------------------------------------------------- */
/* Trigger                                                                    */
/* -------------------------------------------------------------------------- */

interface TabsTriggerProps {
  value: string;
  children: ReactNode;
  disabled?: boolean;
  className?: string;
  icon?: ReactNode;
}

export const TabsTrigger = forwardRef<HTMLButtonElement, TabsTriggerProps>(
  ({ value, children, disabled, className, icon, ...props }, forwardedRef) => {
    const { value: currentValue, onValueChange, variant, size, orientation, activationMode } = useTabsContext();
    const isActive = currentValue === value;
    const buttonRef = useRef<HTMLButtonElement>(null);

    // Sync forwarded ref
    useEffect(() => {
      if (typeof forwardedRef === "function") {
        forwardedRef(buttonRef.current);
      } else if (forwardedRef) {
        forwardedRef.current = buttonRef.current;
      }
    }, [forwardedRef]);

    const handleClick = () => {
      if (!disabled) onValueChange(value);
    };

    const handleKeyDown = (event: React.KeyboardEvent) => {
      if (disabled) return;
      if (activationMode !== "manual") return;

      let nextValue: string | null = null;
      const parent = buttonRef.current?.parentElement;
      const triggers = Array.from(
        (parent?.querySelectorAll('[role="tab"]') || []) as HTMLButtonElement[]
      );
      const currentIndex = triggers.findIndex((t) => t === buttonRef.current);

      switch (event.key) {
        case "ArrowRight":
          if (orientation === "horizontal") {
            event.preventDefault();
            nextValue = triggers[(currentIndex + 1) % triggers.length]?.getAttribute("data-value") || null;
          }
          break;
        case "ArrowLeft":
          if (orientation === "horizontal") {
            event.preventDefault();
            nextValue = triggers[(currentIndex - 1 + triggers.length) % triggers.length]?.getAttribute("data-value") || null;
          }
          break;
        case "ArrowDown":
          if (orientation === "vertical") {
            event.preventDefault();
            nextValue = triggers[(currentIndex + 1) % triggers.length]?.getAttribute("data-value") || null;
          }
          break;
        case "ArrowUp":
          if (orientation === "vertical") {
            event.preventDefault();
            nextValue = triggers[(currentIndex - 1 + triggers.length) % triggers.length]?.getAttribute("data-value") || null;
          }
          break;
        case "Home":
          event.preventDefault();
          nextValue = triggers[0]?.getAttribute("data-value") || null;
          break;
        case "End":
          event.preventDefault();
          nextValue = triggers[triggers.length - 1]?.getAttribute("data-value") || null;
          break;
      }

      if (nextValue) onValueChange(nextValue);
    };

    return (
      <button
        ref={buttonRef}
        role="tab"
        aria-selected={isActive}
        aria-controls={`panel-${value}`}
        id={`trigger-${value}`}
        data-state={isActive ? "active" : "inactive"}
        data-value={value}
        disabled={disabled}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={tabTriggerStyles({ variant, size, className })}
        {...props}
      >
        {icon && <span className="flex-shrink-0" aria-hidden="true">{icon}</span>}
        {children}
        {variant === "line" && isActive && (
          <span className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0.5 h-0.5 rounded-full bg-[var(--color-accent)]" />
        )}
      </button>
    );
  }
);

TabsTrigger.displayName = "TabsTrigger";

/* -------------------------------------------------------------------------- */
/* Content                                                                    */
/* -------------------------------------------------------------------------- */

interface TabsContentProps {
  value: string;
  children: ReactNode;
  className?: string;
  forceMount?: boolean;
}

export const TabsContent = forwardRef<HTMLDivElement, TabsContentProps>(
  ({ value, children, className, forceMount, ...props }, ref) => {
    const { value: currentValue, variant } = useTabsContext();
    const isActive = currentValue === value;
    const mountedRef = useRef(isActive || forceMount);

    if (isActive) mountedRef.current = true;

    if (!mountedRef.current && !forceMount) return null;

    return (
      <div
        ref={ref}
        role="tabpanel"
        id={`panel-${value}`}
        aria-labelledby={`trigger-${value}`}
        data-state={isActive ? "active" : "inactive"}
        data-orientation="horizontal"
        className={tabContentStyles({ animated: true, className })}
        hidden={!isActive}
        tabIndex={0}
        {...props}
      >
        {children}
      </div>
    );
  }
);

TabsContent.displayName = "TabsContent";

/* -------------------------------------------------------------------------- */
/* Compound Export                                                            */
/* -------------------------------------------------------------------------- */

export const Tabs = Object.assign(TabsRoot, {
  List: TabsList,
  Trigger: TabsTrigger,
  Content: TabsContent,
});