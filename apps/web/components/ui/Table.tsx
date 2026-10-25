"use client";

import type { ReactNode, MouseEvent, KeyboardEvent } from "react";
import { useState, useRef, useEffect } from "react";

export interface Column<T> {
  /** Unique column key */
  key: string;
  /** Column header label */
  header: string;
  /** Cell renderer */
  render?: (row: T, index: number) => ReactNode;
  /** Column width */
  width?: string;
  /** Text alignment */
  align?: "left" | "center" | "right";
  /** Whether column is sortable */
  sortable?: boolean;
  /** Whether to hide column on mobile */
  hideOnMobile?: boolean;
}

export interface TableProps<T> {
  /** Table columns */
  columns: Column<T>[];
  /** Table data rows */
  data: T[];
  /** Unique row key extractor */
  rowKey: (row: T) => string;
  /** Row click handler */
  onRowClick?: (row: T, event: MouseEvent | KeyboardEvent) => void;
  /** Selected row keys */
  selectedKeys?: Set<string>;
  /** Called when selection changes */
  onSelectionChange?: (keys: Set<string>) => void;
  /** Whether rows are selectable */
  selectable?: boolean;
  /** Loading state */
  loading?: boolean;
  /** Empty state message */
  emptyMessage?: string;
  /** Empty state icon */
  emptyIcon?: ReactNode;
  /** Additional class names */
  className?: string;
  /** ARIA label for table */
  "aria-label"?: string;
  /** Caption for accessibility */
  caption?: string;
  /** Sticky header */
  stickyHeader?: boolean;
  /** Row class name function */
  rowClassName?: (row: T, index: number) => string;
}

export function Table<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  selectedKeys = new Set(),
  onSelectionChange,
  selectable = false,
  loading = false,
  emptyMessage = "No data",
  emptyIcon,
  className = "",
  "aria-label": ariaLabel,
  caption,
  stickyHeader = false,
  rowClassName,
}: TableProps<T>) {
  const handleSelectAll = () => {
    if (!onSelectionChange) return;
    const newKeys = new Set(selectedKeys);
    if (newKeys.size === data.length) {
      newKeys.clear();
    } else {
      data.forEach((row) => newKeys.add(rowKey(row)));
    }
    onSelectionChange(newKeys);
  };

  // Track previous data length to detect changes
  const prevDataLengthRef = useRef(data.length);
  useEffect(() => {
    prevDataLengthRef.current = data.length;
  }, [data.length]);

  const handleSelectRow = (row: T) => {
    if (!onSelectionChange) return;
    const key = rowKey(row);
    const newKeys = new Set(selectedKeys);
    if (newKeys.has(key)) {
      newKeys.delete(key);
    } else {
      newKeys.add(key);
    }
    onSelectionChange(newKeys);
  };

  const isRowSelected = (row: T) => selectedKeys.has(rowKey(row));

  return (
    <div className={`table-container ${className}`} role="region" aria-label={ariaLabel} tabIndex={0}>
      {caption && <caption className="sr-only">{caption}</caption>}
      <div className="overflow-x-auto">
        <table className="table" role="grid">
          <thead className={stickyHeader ? "sticky top-0 z-10" : ""}>
            <tr>
              {selectable && (
                <th scope="col" className="w-10 px-3">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded-[var(--radius-sm)] border-[var(--color-border-default)] text-[var(--color-accent-fg)] focus:ring-[var(--color-accent-fg)] focus:ring-offset-2 focus:ring-offset-[var(--color-canvas)]"
                    checked={data.length > 0 && selectedKeys.size === data.length}
                    onChange={handleSelectAll}
                    aria-label="Select all rows"
                  />
                </th>
              )}
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  style={{ width: column.width, textAlign: column.align }}
                  className={`
                    ${column.sortable ? "cursor-pointer select-none hover:text-[var(--color-fg-default)]" : ""}
                    ${column.hideOnMobile ? "hidden md:table-cell" : ""}
                  `}
                  aria-sort={column.sortable ? "none" : undefined}
                >
                  <div className="flex items-center gap-1.5">
                    {column.header}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={columns.length + (selectable ? 1 : 0)} className="py-12 text-center">
                  <div className="inline-flex items-center gap-2 text-[var(--color-fg-muted)]">
                    <svg className="h-5 w-5 animate-spin text-[var(--color-accent-fg)]" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Loading...
                  </div>
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (selectable ? 1 : 0)} className="py-12 text-center">
                  <div className="empty-state">
                    {emptyIcon || (
                      <svg className="empty-state-icon" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                        <path d="M1.5 2A1.5 1.5 0 0 1 3 0.5h10A1.5 1.5 0 0 1 14.5 2v12a1.5 1.5 0 0 1-1.5 1.5H3A1.5 1.5 0 0 1 1.5 14v-12zm13.5 1a.5.5 0 0 0-.969-.206L8 7.168 3.47 3.704a.31.31 0 0 0-.21 0l-.41.401A.31.31 0 0 0 3 4.5v7.09l5.16 2.968a.5.5 0 0 0 .832 0L13 8.5v-5.5zm-2 6.5a.5.5 0 0 1 0-1h-7a.5.5 0 0 1 0 1h7z" />
                      </svg>
                    )}
                    <p className="empty-state-title">{data.length === 0 ? "No data" : "Loading..."}</p>
                    <p className="empty-state-description">{emptyMessage}</p>
                  </div>
                </td>
              </tr>
            ) : (
              data.map((row, index) => {
                const key = rowKey(row);
                const isSelected = isRowSelected(row);

                return (
                  <tr
                    key={key}
                    className={`
                      transition-colors duration-80 ease-out
                      ${isSelected ? "bg-[var(--color-accent-muted)]" : "hover:bg-[var(--color-canvas-subtle)]"}
                      ${onRowClick ? "cursor-pointer" : ""}
                      ${rowClassName ? rowClassName(row, index) : ""}
                    `}
                    onClick={(e) => onRowClick?.(row, e)}
                    onKeyDown={(e) => {
                      if ((e.key === "Enter" || e.key === " ") && onRowClick) {
                        e.preventDefault();
                        onRowClick(row, e);
                      }
                    }}
                    tabIndex={onRowClick ? 0 : undefined}
                    style={{ backgroundColor: isSelected ? "var(--color-accent-muted)" : undefined }}
                  >
                    {selectable && (
                      <td className="px-3">
                        <input
                          type="checkbox"
                          className="h-4 w-4 rounded-[var(--radius-sm)] border-[var(--color-border-default)] text-[var(--color-accent-fg)] focus:ring-[var(--color-accent-fg)] focus:ring-offset-2 focus:ring-offset-[var(--color-canvas)]"
                          checked={isSelected}
                          onChange={() => handleSelectRow(row)}
                          onClick={(e) => e.stopPropagation()}
                          aria-label={`Select row ${index + 1}`}
                        />
                      </td>
                    )}
                    {columns.map((column) => (
                      <td
                        key={column.key}
                        style={{ textAlign: column.align }}
                        className={`${column.hideOnMobile ? "hidden md:table-cell" : ""}`}
                      >
                        {column.render ? column.render(row, index) : String((row as any)[column.key])}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Helper hook for selection state
export function useTableSelection<T>() {
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [data, setData] = useState<T[]>([]);

  function syncSelection(newData: T[], rowKey: (row: T) => string) {
    setData(newData);
    // Remove keys for rows that no longer exist
    const validKeys = new Set(newData.map(rowKey));
    setSelectedKeys((prev) => {
      const newSet = new Set<string>();
      prev.forEach((key) => {
        if (validKeys.has(key)) newSet.add(key);
      });
      return newSet;
    });
  }

  return {
    selectedKeys,
    setSelectedKeys,
    data,
    setData,
    syncSelection,
  };
}