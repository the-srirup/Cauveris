"use client";

import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  cloneElement,
  Fragment,
  type ReactNode,
} from "react";

export interface DropdownItem {
  /** Unique item key */
  key?: string;
  /** Item label */
  label?: string;
  /** Item description */
  description?: string;
  /** Leading icon */
  icon?: ReactNode;
  /** Leading icon alias */
  leadingIcon?: ReactNode;
  /** Trailing element (e.g., keyboard shortcut) */
  trailing?: ReactNode;
  /** Whether item is disabled */
  disabled?: boolean;
  /** Whether item is destructive */
  danger?: boolean;
  /** Whether item is a divider */
  divider?: boolean;
  /** Section label (for grouped items) */
  section?: string;
  /** On click handler */
  onClick?: () => void;
}

export type DropdownTriggerRender = (props: { open: boolean; onClick: () => void }) => ReactNode;

export interface DropdownProps {
  /** Trigger element */
  children: ReactNode | DropdownTriggerRender;
  /** Dropdown items */
  items: DropdownItem[];
  /** Dropdown alignment */
  align?: "left" | "right";
  /** Whether dropdown is open (controlled) */
  open?: boolean;
  /** Default open state (uncontrolled) */
  defaultOpen?: boolean;
  /** Called when open state changes */
  onOpenChange?: (open: boolean) => void;
  /** Called when item is selected */
  onSelect?: (key: string, item: DropdownItem) => void;
  /** Additional class names */
  className?: string;
  /** ARIA label for dropdown */
  "aria-label"?: string;
}

export function Dropdown({
  children,
  items,
  align = "right",
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  onSelect,
  className = "",
  "aria-label": ariaLabel = "Menu",
}: DropdownProps) {
  const [internalOpen, setInternalOpen] = useState(defaultOpen);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;

  const dropdownRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const focusedIndex = useRef<number>(-1);

  const setOpen = useCallback(
    (newOpen: boolean) => {
      if (!isControlled) {
        setInternalOpen(newOpen);
      }
      onOpenChange?.(newOpen);
    },
    [isControlled, onOpenChange]
  );

  // Close on click outside
  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open, setOpen]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [open, setOpen]);

  const handleTriggerClick = () => {
    setOpen(!open);
  };

  const handleItemClick = (key: string | undefined, item: DropdownItem) => {
    if (item.disabled || item.divider) return;
    let clicked = false;
    const wrappedItem = item.onClick
      ? {
          ...item,
          onClick: () => {
            clicked = true;
            item.onClick?.();
          },
        }
      : item;

    onSelect?.(key || "", wrappedItem);
    if (!clicked && item.onClick) {
      item.onClick();
    }
    setOpen(false);
    triggerRef.current?.focus();
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    const enabledItems = items.filter((i) => !i.disabled && !i.divider);
    if (enabledItems.length === 0) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        focusedIndex.current = (focusedIndex.current + 1) % enabledItems.length;
        const nextItem = enabledItems[focusedIndex.current];
        if (nextItem.key) itemRefs.current.get(nextItem.key)?.focus();
        break;

      case "ArrowUp":
        e.preventDefault();
        focusedIndex.current =
          focusedIndex.current <= 0 ? enabledItems.length - 1 : focusedIndex.current - 1;
        const prevItem = enabledItems[focusedIndex.current];
        if (prevItem.key) itemRefs.current.get(prevItem.key)?.focus();
        break;

      case "Home":
        e.preventDefault();
        focusedIndex.current = 0;
        const firstItem = enabledItems[0];
        if (firstItem?.key) itemRefs.current.get(firstItem.key)?.focus();
        break;

      case "End":
        e.preventDefault();
        focusedIndex.current = enabledItems.length - 1;
        const lastItem = enabledItems[enabledItems.length - 1];
        if (lastItem?.key) itemRefs.current.get(lastItem.key)?.focus();
        break;

      case "Tab":
        setOpen(false);
        break;
    }
  };

  // Reset focus index when closed
  useEffect(() => {
    if (!open) {
      focusedIndex.current = -1;
    }
  }, [open]);

  // Build items with sections
  const groupedItems = items.reduce<Record<string, DropdownItem[]>>((acc, item) => {
    const section = item.section || "default";
    if (!acc[section]) acc[section] = [];
    acc[section].push(item);
    return acc;
  }, {});

  const renderTrigger = (isOpen: boolean) => {
    if (typeof children === "function") {
      return (children as DropdownTriggerRender)({ open: isOpen, onClick: handleTriggerClick });
    }
    return cloneElement(children as React.ReactElement<any>, {
      onClick: handleTriggerClick,
      ref: triggerRef,
      "aria-haspopup": "menu",
      "aria-expanded": isOpen,
      tabIndex: 0,
    });
  };

  if (!open) {
    return (
      <div className={`relative inline-block ${className}`} ref={dropdownRef}>
        {renderTrigger(false)}
      </div>
    );
  }

  return (
    <div className={`relative inline-block ${className}`} ref={dropdownRef}>
      {renderTrigger(true)}
      <div
        className={`
          absolute top-full z-[var(--z-dropdown)] mt-1.5 min-w-[180px] max-w-[320px]
          ${align === "right" ? "right-0" : "left-0"}
          bg-[var(--color-canvas-inset)] border border-[var(--color-border-default)]
          rounded-[var(--radius-lg)] shadow-[var(--shadow-lg)]
          py-1 animate-fade-in
        `}
        role="menu"
        aria-label={ariaLabel}
        onKeyDown={handleKeyDown}
      >
        {Object.entries(groupedItems).map(([sectionName, sectionItems], sectionIndex) => (
          <Fragment key={sectionName}>
            {sectionName !== "default" && (
              <div className="px-2 py-1 text-[10px] font-semibold text-[var(--color-fg-subtle)] uppercase tracking-wider">
                {sectionName}
              </div>
            )}
            {sectionIndex > 0 && sectionName !== "default" && (
              <div className="dropdown-divider" role="separator" />
            )}
            {sectionItems.map((item, itemIndex) => {
              const itemKey = item.key || `item-${sectionIndex}-${itemIndex}`;
              const itemIcon = item.leadingIcon || item.icon;

              return item.divider ? (
                <div key={`${sectionName}-divider-${itemIndex}`} className="dropdown-divider my-1" role="separator" />
              ) : (
                <button
                  key={itemKey}
                  ref={(el) => {
                    if (el) itemRefs.current.set(itemKey, el);
                    else itemRefs.current.delete(itemKey);
                  }}
                  type="button"
                  role="menuitem"
                  disabled={item.disabled}
                  onClick={() => handleItemClick(itemKey, item)}
                  className={`
                    w-full flex items-center gap-2 px-2 py-1.5 text-sm text-[var(--color-fg-default)]
                    rounded-[var(--radius-sm)]
                    transition-colors duration-80 ease-out
                    focus-visible:outline-none focus-visible:bg-[var(--color-canvas-subtle)]
                    ${item.danger ? "text-[var(--color-danger-fg)] hover:bg-[var(--color-danger-muted)]" : "hover:bg-[var(--color-canvas-subtle)]"}
                    ${item.disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                  `}
                  tabIndex={-1}
                >
                  {itemIcon && <span className="flex-shrink-0 h-4 w-4" aria-hidden="true">{itemIcon}</span>}
                  <div className="flex-1 min-w-0 text-left">
                    <span className="truncate block">{item.label}</span>
                    {item.description && (
                      <span className="text-[11px] text-[var(--color-fg-subtle)] truncate block">{item.description}</span>
                    )}
                  </div>
                  {item.trailing && <span className="text-[11px] text-[var(--color-fg-subtle)] flex-shrink-0">{item.trailing}</span>}
                </button>
              );
            })}
          </Fragment>
        ))}
      </div>
    </div>
  );
}