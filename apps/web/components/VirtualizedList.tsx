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
  overscanCount = 5,
  className = "",
  style,
}: VirtualizedListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  // Calculate visible range
  const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - overscanCount);
  const visibleCount = Math.ceil(height / itemHeight) + overscanCount * 2;
  const endIndex = Math.min(items.length, startIndex + visibleCount);
  const visibleItems = items.slice(startIndex, endIndex);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
  }, []);

  const totalHeight = items.length * itemHeight;
  const offsetY = startIndex * itemHeight;

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
      <div style={{ height: totalHeight, position: "relative" }}>
        <div style={{ transform: `translateY(${offsetY}px)`, position: "absolute", top: 0, left: 0, right: 0 }}>
          {visibleItems.map((item, i) => {
            const index = startIndex + i;
            const itemStyle: React.CSSProperties = {
              position: "absolute",
              top: index * itemHeight,
              left: 0,
              right: 0,
              height: itemHeight,
            };
            return <div key={index} style={itemStyle}>{renderItem(item, index, itemStyle)}</div>;
          })}
        </div>
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

  // Calculate visible range
  const startRow = Math.max(0, Math.floor(scrollTop / rowHeight) - overscanCount);
  const visibleRowCount = Math.ceil(height / rowHeight) + overscanCount * 2;
  const endRow = Math.min(Math.ceil(items.length / columnCount), startRow + visibleRowCount);

  const startCol = Math.max(0, Math.floor(scrollLeft / columnWidth) - overscanCount);
  const visibleColCount = Math.ceil((typeof width === "number" ? width : 800) / columnWidth) + overscanCount * 2;
  const endCol = Math.min(columnCount, startCol + visibleColCount);

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(e.currentTarget.scrollTop);
    setScrollLeft(e.currentTarget.scrollLeft);
  }, []);

  const totalRows = Math.ceil(items.length / columnCount);
  const totalHeight = totalRows * rowHeight;
  const totalWidth = columnCount * columnWidth;

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