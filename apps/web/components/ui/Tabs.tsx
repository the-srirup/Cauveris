"use client";

import * as React from "react";
import type { ReactNode } from "react";

export interface TabProps {
  /** Tab label */
  label: string;
  /** Tab content */
  children: ReactNode;
  /** Tab key for identification */
  key: string;
  /** Whether tab is disabled */
  disabled?: boolean;
  /** Icon to show before label */
  icon?: ReactNode;
}

export interface TabsProps {
  /** Tab configurations */
  children: ReactNode;
  /** Default active tab key */
  defaultActiveKey?: string;
  /** Controlled active tab key */
  activeKey?: string;
  /** Called when active tab changes */
  onChange?: (key: string) => void;
  /** Visual variant */
  variant?: "default" | "bordered" | "pills";
  /** Alignment */
  align?: "start" | "center" | "end";
  /** Additional class names */
  className?: string;
  /** ARIA label for the tab list */
  "aria-label"?: string;
}

export interface TabsContextValue {
  activeKey: string;
  variant: string;
  onChange: (key: string) => void;
  registerTab: (key: string) => void;
  unregisterTab: (key: string) => void;
}

import { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) {
    throw new Error("Tabs compound components must be used within Tabs");
  }
  return context;
}

export function Tabs({
  children,
  defaultActiveKey,
  activeKey: controlledActiveKey,
  onChange,
  variant = "default",
  align = "start",
  className = "",
  "aria-label": ariaLabel,
}: TabsProps) {
  const isControlled = controlledActiveKey !== undefined;
  const [uncontrolledActiveKey, setUncontrolledActiveKey] = useState(defaultActiveKey || "");
  const activeKey = isControlled ? controlledActiveKey : uncontrolledActiveKey;
  const registeredTabs = useRef<Set<string>>(new Set());

  const handleChange = useCallback(
    (key: string) => {
      if (!isControlled) {
        setUncontrolledActiveKey(key);
      }
      onChange?.(key);
    },
    [isControlled, onChange]
  );

  const registerTab = useCallback((key: string) => {
    registeredTabs.current.add(key);
    // Auto-select first tab if none selected
    if (!activeKey && registeredTabs.current.size === 1) {
      handleChange(key);
    }
  }, [activeKey, handleChange]);

  const unregisterTab = useCallback((key: string) => {
    registeredTabs.current.delete(key);
  }, []);

  const contextValue: TabsContextValue = {
    activeKey,
    variant,
    onChange: handleChange,
    registerTab,
    unregisterTab,
  };

  const alignClasses = {
    start: "justify-start",
    center: "justify-center",
    end: "justify-end",
  };

  let hasTabList = false;
  const tabListChildren: ReactNode[] = [];
  const panelChildren: ReactNode[] = [];
  const otherChildren: ReactNode[] = [];

  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) {
      otherChildren.push(child);
      return;
    }
    if (child.type === TabList) {
      hasTabList = true;
      otherChildren.push(child);
    } else if (child.type === TabPanel) {
      const itemKey =
        (child.props as any).id ||
        (child.props as any).value ||
        (child.props as any).tabKey ||
        (child.key != null ? String(child.key).replace(/^\.\$/, "") : undefined);
      panelChildren.push(
        itemKey ? React.cloneElement(child, { id: itemKey, value: itemKey, tabKey: itemKey } as any) : child
      );
    } else if (child.type === TabButton || child.type === Tab) {
      const itemKey =
        (child.props as any).id ||
        (child.props as any).value ||
        (child.props as any).tabKey ||
        (child.key != null ? String(child.key).replace(/^\.\$/, "") : undefined);
      tabListChildren.push(
        itemKey ? React.cloneElement(child, { id: itemKey, value: itemKey, tabKey: itemKey } as any) : child
      );
    } else {
      otherChildren.push(child);
    }
  });

  return (
    <TabsContext.Provider value={contextValue}>
      <div className={className}>
        {hasTabList || (tabListChildren.length === 0 && panelChildren.length === 0) ? (
          children
        ) : (
          <>
            {tabListChildren.length > 0 && (
              <div
                role="tablist"
                aria-label={ariaLabel}
                className={`
                  flex ${alignClasses[align]} gap-1
                  ${variant === "bordered" ? "border-b border-[var(--color-border-default)]" : ""}
                  ${variant === "pills" ? "bg-[var(--color-canvas-subtle)] p-1 rounded-[var(--radius-md)]" : ""}
                `}
              >
                {tabListChildren}
              </div>
            )}
            {(panelChildren.length > 0 || otherChildren.length > 0) && (
              <div className="mt-4">
                {panelChildren}
                {otherChildren}
              </div>
            )}
          </>
        )}
      </div>
    </TabsContext.Provider>
  );
}

export function TabList({ children, className = "", "aria-label": ariaLabel }: { children: ReactNode; className?: string; "aria-label"?: string }) {
  const { variant } = useTabsContext();

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={`
        flex gap-1
        ${className}
        ${variant === "bordered" ? "border-b border-[var(--color-border-default)]" : ""}
        ${variant === "pills" ? "bg-[var(--color-canvas-subtle)] p-1 rounded-[var(--radius-md)]" : ""}
      `}
    >
      {children}
    </div>
  );
}

export function Tab({ children, ...props }: { children: ReactNode } & Omit<TabProps, "children">) {
  return <TabButton {...props}>{children}</TabButton>;
}

export function TabButton({
  label,
  disabled = false,
  icon,
  children,
  id,
  value,
  tabKey,
  ...restProps
}: TabProps & { id?: string; value?: string; tabKey?: string }) {
  const { activeKey, variant, onChange, registerTab, unregisterTab } = useTabsContext();
  const key = id || value || tabKey || (restProps as any).key || label || "";
  const isActive = Boolean(key && activeKey === key);

  useEffect(() => {
    if (key) {
      registerTab(key);
      return () => unregisterTab(key);
    }
  }, [key, registerTab, unregisterTab]);

  const handleClick = () => {
    if (!disabled && key) {
      onChange(key);
    }
  };

  const variantStyles = {
    default: `
      ${isActive ? "text-[var(--color-accent-fg)]" : "text-[var(--color-fg-muted)]"}
      hover:text-[var(--color-fg-default)]
      border-b-2 ${isActive ? "border-[var(--color-accent-fg)]" : "border-transparent"}
      pb-2 -mb-px
    `,
    bordered: `
      ${isActive ? "text-[var(--color-accent-fg)]" : "text-[var(--color-fg-muted)]"}
      hover:text-[var(--color-fg-default)]
      border-b-2 ${isActive ? "border-[var(--color-accent-fg)]" : "border-transparent"}
      pb-2 -mb-px
    `,
    pills: `
      ${isActive ? "bg-[var(--color-canvas)] text-[var(--color-fg-default)] shadow-sm" : "text-[var(--color-fg-muted)]"}
      hover:text-[var(--color-fg-default)]
      hover:bg-[var(--color-canvas-subtle)]
      px-3 py-1.5 rounded-[var(--radius-sm)]
    `,
  };

  const baseClasses = `
    flex items-center gap-1.5
    font-medium text-sm
    transition-colors duration-80 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent-fg)]
    focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
    ${disabled ? "opacity-50 cursor-not-allowed pointer-events-none" : "cursor-pointer"}
    ${variantStyles[variant as keyof typeof variantStyles] || variantStyles.default}
  `;

  return (
    <button
      role="tab"
      id={`tab-${key}`}
      aria-selected={isActive}
      aria-controls={`panel-${key}`}
      tabIndex={isActive ? 0 : -1}
      onClick={handleClick}
      disabled={disabled}
      className={baseClasses}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {label || children}
    </button>
  );
}

export function TabPanel({
  children,
  className = "",
  id,
  value,
  tabKey,
  ...restProps
}: { children: ReactNode; key?: string; id?: string; value?: string; tabKey?: string; className?: string }) {
  const { activeKey } = useTabsContext();
  const key = id || value || tabKey || (restProps as any).key || "";
  const isActive = Boolean(key && activeKey === key);

  if (!isActive) return null;

  return (
    <div
      role="tabpanel"
      id={`panel-${key}`}
      aria-labelledby={`tab-${key}`}
      tabIndex={0}
      className={className}
    >
      {children}
    </div>
  );
}