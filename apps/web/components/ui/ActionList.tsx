"use client";

import React, { Fragment, type ReactNode, type KeyboardEvent } from "react";

export interface ActionListItem {
  /** Unique item key */
  key: string;
  /** Item label */
  label: string;
  /** Item description */
  description?: string;
  /** Leading icon */
  leadingIcon?: ReactNode;
  /** Trailing element (e.g., keyboard shortcut) */
  trailing?: ReactNode;
  /** Trailing icon */
  trailingIcon?: ReactNode;
  /** Whether item is disabled */
  disabled?: boolean;
  /** Whether item is destructive */
  danger?: boolean;
  /** Whether item is a divider */
  divider?: boolean;
  /** Section label */
  section?: string;
  /** Whether item is selected */
  selected?: boolean;
  /** Whether to show checkmark when selected */
  showSelection?: boolean;
  /** Custom render function */
  render?: () => ReactNode;
}

export interface ActionListProps {
  /** Items to display */
  items: ActionListItem[];
  /** Called when item is selected */
  onSelect?: (key: string, item: ActionListItem) => void;
  /** Whether multiple items can be selected */
  multiple?: boolean;
  /** Currently selected keys (controlled) */
  selectedKeys?: Set<string>;
  /** Additional class names */
  className?: string;
  /** ARIA label for the list */
  "aria-label"?: string;
  /** Whether to show checkboxes for multiple selection */
  showCheckboxes?: boolean;
  /** Item role: menu or listbox */
  role?: "menu" | "listbox";
}

export function ActionList({
  items,
  onSelect,
  multiple = false,
  selectedKeys = new Set(),
  className = "",
  "aria-label": ariaLabel,
  showCheckboxes = false,
  role = "menu",
}: ActionListProps) {
  // Group items by section
  const groupedItems = items.reduce<Record<string, ActionListItem[]>>((acc, item) => {
    const section = item.section || "default";
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  const handleKeyDown = (event: KeyboardEvent<HTMLElement>, item: ActionListItem, index: number, sectionItems: ActionListItem[]) => {
    const enabledItems = sectionItems.filter((i) => !i.disabled && !i.divider);
    const enabledIndices = enabledItems.map((i) => sectionItems.indexOf(i));

    switch (event.key) {
      case "Enter":
      case " ":
        event.preventDefault();
        if (!item.disabled && !item.divider) {
          handleSelect(item);
        }
        break;
      case "ArrowDown":
        event.preventDefault();
        focusNext(enabledItems, enabledIndices, index, 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusNext(enabledItems, enabledIndices, index, -1);
        break;
      case "Home":
        event.preventDefault();
        focusIndex(enabledItems, 0);
        break;
      case "End":
        event.preventDefault();
        focusIndex(enabledItems, enabledItems.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        (event.target as HTMLElement).blur();
        break;
    }
  };

  const focusNext = (enabledItems: ActionListItem[], enabledIndices: number[], currentIndex: number, direction: number) => {
    const currentEnabledIndex = enabledIndices.indexOf(currentIndex);
    const nextEnabledIndex = currentEnabledIndex + direction;
    if (nextEnabledIndex >= 0 && nextEnabledIndex < enabledItems.length) {
      const targetItem = enabledItems[nextEnabledIndex];
      const targetElement = document.querySelector(`[data-action-key="${targetItem.key}"]`) as HTMLElement;
      targetElement?.focus();
    }
  };

  const focusIndex = (enabledItems: ActionListItem[], index: number) => {
    if (enabledItems[index]) {
      const targetElement = document.querySelector(`[data-action-key="${enabledItems[index].key}"]`) as HTMLElement;
      targetElement?.focus();
    }
  };

  const handleSelect = (item: ActionListItem) => {
    if (onSelect) {
      onSelect(item.key, item);
    }
  };

  return (
    <div
      role={role}
      aria-label={ariaLabel}
      className={`action-list ${className}`}
      tabIndex={0}
    >
      {Object.entries(groupedItems).map(([sectionName, sectionItems]) => (
        <Fragment key={sectionName}>
          {sectionName !== "default" && (
            <div className="px-2 py-1.5 text-[10px] font-semibold text-[var(--color-fg-subtle)] uppercase tracking-wider">
              {sectionName}
            </div>
          )}
          {sectionItems.map((item, index) =>
            item.divider ? (
              <div key={`${sectionName}-divider-${index}`} className="h-px bg-[var(--color-border-muted)] my-1" role="separator" />
            ) : item.render ? (
              <div key={item.key} className="px-2 py-1" data-action-key={item.key} role={role === "menu" ? "menuitem" : "option"}>
                {item.render()}
              </div>
            ) : (
              <button
                key={item.key}
                type="button"
                role={role === "menu" ? "menuitem" : "option"}
                aria-selected={selectedKeys.has(item.key)}
                aria-disabled={item.disabled}
                disabled={item.disabled}
                onClick={() => handleSelect(item)}
                onKeyDown={(e) => handleKeyDown(e, item, index, sectionItems)}
                data-action-key={item.key}
                className={`
                  w-full flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--color-fg-default)]
                  rounded-[var(--radius-sm)]
                  transition-colors duration-80 ease-out
                  focus-visible:outline-none focus-visible:bg-[var(--color-canvas-subtle)]
                  ${item.danger ? "text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)]" : "hover:bg-[var(--color-canvas-subtle)]"}
                  ${item.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                  ${selectedKeys.has(item.key) ? "bg-[var(--color-accent-muted)]" : ""}
                `}
                tabIndex={-1}
              >
                {showCheckboxes && (
                  <span className="flex-shrink-0 h-4 w-4 flex items-center justify-center">
                    {selectedKeys.has(item.key) ? (
                      <svg className="h-3.5 w-3.5 text-[var(--color-accent-fg)]" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                        <path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z" />
                      </svg>
                    ) : (
                      <svg className="h-3.5 w-3.5 text-[var(--color-fg-subtle)]" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
                        <rect x="2" y="2" width="12" height="12" rx="2" />
                      </svg>
                    )}
                  </span>
                )}
                {item.leadingIcon && <span className="flex-shrink-0 h-4 w-4" aria-hidden="true">{item.leadingIcon}</span>}
                <div className="flex-1 min-w-0 text-left">
                  <span className="truncate block">{item.label}</span>
                  {item.description && (
                    <span className="text-[11px] text-[var(--color-fg-subtle)] truncate block">{item.description}</span>
                  )}
                </div>
                {item.trailing && <span className="text-[11px] text-[var(--color-fg-subtle)] flex-shrink-0">{item.trailing}</span>}
                {item.trailingIcon && <span className="flex-shrink-0 h-4 w-4" aria-hidden="true">{item.trailingIcon}</span>}
              </button>
            )
          )}
        </Fragment>
      ))}
    </div>
  );
}

export interface ActionListItemProps {
  item: ActionListItem;
  selected?: boolean;
  onClick?: () => void;
  className?: string;
  role?: "menuitem" | "option";
}

export function ActionListItem({ item, selected = false, onClick, className = "", role = "menuitem" }: ActionListItemProps) {
  return (
    <button
      type="button"
      role={role}
      aria-selected={selected}
      aria-disabled={item.disabled}
      disabled={item.disabled}
      onClick={onClick}
      className={`
        w-full flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--color-fg-default)]
        rounded-[var(--radius-sm)]
        transition-colors duration-80 ease-out
        focus-visible:outline-none focus-visible:bg-[var(--color-canvas-subtle)]
        ${item.danger ? "text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)]" : "hover:bg-[var(--color-canvas-subtle)]"}
        ${item.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
        ${selected ? "bg-[var(--color-accent-muted)]" : ""}
        ${className}
      `}
    >
      {item.leadingIcon && <span className="flex-shrink-0 h-4 w-4" aria-hidden="true">{item.leadingIcon}</span>}
      <div className="flex-1 min-w-0 text-left">
        <span className="truncate block">{item.label}</span>
        {item.description && (
          <span className="text-[11px] text-[var(--color-fg-subtle)] truncate block">{item.description}</span>
        )}
      </div>
      {item.trailing && <span className="text-[11px] text-[var(--color-fg-subtle)] flex-shrink-0">{item.trailing}</span>}
      {item.trailingIcon && <span className="flex-shrink-0 h-4 w-4" aria-hidden="true">{item.trailingIcon}</span>}
    </button>
  );
}

export interface ActionListSectionProps {
  /** Section label */
  label: string;
  /** Section items */
  children: ReactNode;
  /** Additional class names */
  className?: string;
}

export function ActionListSection({ label, children, className = "" }: ActionListSectionProps) {
  return (
    <div className={className}>
      <div className="px-2 py-1.5 text-[10px] font-semibold text-[var(--color-fg-subtle)] uppercase tracking-wider">
        {label}
      </div>
      <div role="group">{children}</div>
    </div>
  );
}

export interface ActionListDividerProps {
  className?: string;
}

export function ActionListDivider({ className = "" }: ActionListDividerProps) {
  return <div className={`h-px bg-[var(--color-border-muted)] my-1 ${className}`} role="separator" />;
}