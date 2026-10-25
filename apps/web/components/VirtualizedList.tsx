"use client";

import { useMemo, useRef, useCallback, useState, useEffect } from "react";

interface VirtualizedListProps<T> {
  items: T[];
  itemHeight: number;
  renderItem: (item: T, index: number, style: React.CSSProperties) => React.ReactNode;
  height: number;
  width?: number | string;
  overscanCount?: number;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Simple virtualized list implementation without external dependencies.
 * Renders only visible items + overscan buffer.
 */
export function VirtualizedList<T>({
  items,
  itemHeight,
  renderItem,
  height,
  width = "100%",
  overscanCount = 4,
  className = "",
  style,
}: VirtualizedListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // A zero item height makes the range maths divide by zero (Infinity) and
  // renders the entire list instead of a window of it.
  const safeItemHeight = itemHeight > 0 ? itemHeight : 1;

  const totalHeight = items.length * safeItemHeight;
  const maxScroll = Math.max(0, totalHeight - height);

  // Clamp scrollTop to valid range to prevent overscroll disappearing bug
  const clampedScrollTop = Math.max(0, Math.min(scrollTop, maxScroll));

  // Calculate visible range with clamped values
  const rawStartIndex = Math.floor(clampedScrollTop / safeItemHeight);
  const maxStartIndex = Math.max(0, items.length - 1);
  const startIndex = Math.max(0, Math.min(maxStartIndex, rawStartIndex - overscanCount));
  const visibleCount = Math.ceil(height / safeItemHeight) + overscanCount * 2;
  const endIndex = Math.max(startIndex, Math.min(items.length, startIndex + visibleCount));
  const visibleItems = items.slice(startIndex, endIndex);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  // When items change or filter changes, ensure scroll position is not beyond the new total height
  useEffect(() => {
    if (containerRef.current) {
      if (containerRef.current.scrollTop > maxScroll) {
        containerRef.current.scrollTop = maxScroll;
        setScrollTop(maxScroll);
      }
    }
  }, [items.length, maxScroll]);

  return (
    <div
      ref={containerRef}
      className={`scrollbar-thin ${className}`}
      style={{
        height,
        width,
        overflowY: "auto",
        overflowX: "hidden",
        position: "relative",
        WebkitOverflowScrolling: "touch",
        ...style,
      }}
      onScroll={handleScroll}
    >
      <div style={{ height: totalHeight, minHeight: "100%", position: "relative", width: "100%" }}>
        {visibleItems.map((item, i) => {
          const index = startIndex + i;
          const itemStyle: React.CSSProperties = {
            position: "absolute",
            top: index * itemHeight,
            left: 0,
            right: 0,
            height: itemHeight,
            boxSizing: "border-box",
          };
          return (
            <div key={index} style={itemStyle}>
              {renderItem(item, index, { width: "100%", height: "100%", boxSizing: "border-box" })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

interface VirtualizedGridProps<T> {
  items: T[];
  columnCount: number;
  columnWidth: number;
  rowHeight: number;
  renderItem: (item: T, index: number, style: React.CSSProperties) => React.ReactNode;
  height: number;
  width?: number | string;
  overscanCount?: number;
  className?: string;
  style?: React.CSSProperties;
}

export function VirtualizedGrid<T>({
  items,
  columnCount,
  columnWidth,
  rowHeight,
  renderItem,
  height,
  width = "100%",
  overscanCount = 5,
  className = "",
  style,
}: VirtualizedGridProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [scrollLeft, setScrollLeft] = useState(0);

  // Guard against degenerate geometry: a zero row/column height or column count
  // produces Infinity/NaN in the range maths, and a scroll position past the
  // end of the content produced a *negative* range length - `Array(-3)` throws
  // "Invalid array length" and takes the whole page down.
  const safeRowHeight = rowHeight > 0 ? rowHeight : 1;
  const safeColumnWidth = columnWidth > 0 ? columnWidth : 1;
  const safeColumnCount = columnCount > 0 ? columnCount : 1;

  const totalRows = Math.ceil(items.length / safeColumnCount);
  const totalHeight = totalRows * safeRowHeight;
  const totalWidth = safeColumnCount * safeColumnWidth;

  // Calculate visible range
  const startRow = Math.max(0, Math.min(totalRows, Math.floor(scrollTop / safeRowHeight) - overscanCount));
  const visibleRowCount = Math.ceil(height / safeRowHeight) + overscanCount * 2;
  const endRow = Math.max(startRow, Math.min(totalRows, startRow + visibleRowCount));

  const startCol = Math.max(0, Math.min(safeColumnCount, Math.floor(scrollLeft / safeColumnWidth) - overscanCount));
  const visibleColCount =
    Math.ceil((typeof width === "number" ? width : 800) / safeColumnWidth) + overscanCount * 2;
  const endCol = Math.max(startCol, Math.min(safeColumnCount, startCol + visibleColCount));

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
    setScrollLeft(e.currentTarget.scrollLeft);
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        height,
        width,
        overflow: "auto",
        position: "relative",
        ...style,
      }}
      onScroll={handleScroll}
    >
      <div style={{ height: totalHeight, width: totalWidth, position: "relative" }}>
        {[...Array(endRow - startRow)].map((_, rowIdx) => {
          const row = startRow + rowIdx;
          return (
            <div key={`row-${row}`} style={{ position: "absolute", top: row * rowHeight, left: 0, right: 0, height: rowHeight, display: "flex" }}>
              {[...Array(endCol - startCol)].map((_, colIdx) => {
                const col = startCol + colIdx;
                const index = row * columnCount + col;
                if (index >= items.length) return null;
                const itemStyle: React.CSSProperties = {
                  position: "absolute",
                  left: col * columnWidth,
                  top: 0,
                  width: columnWidth,
                  height: rowHeight,
                };
                return (
                  <div key={`cell-${index}`} style={itemStyle}>
                    {renderItem(items[index], index, itemStyle)}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}