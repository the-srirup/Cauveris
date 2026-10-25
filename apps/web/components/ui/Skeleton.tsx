"use client";

export interface SkeletonProps {
  /** Width of skeleton */
  width?: string | number;
  /** Height of skeleton */
  height?: string | number;
  /** Border radius */
  radius?: "none" | "sm" | "md" | "lg" | "full";
  /** Animation variant */
  variant?: "wave" | "pulse" | "none";
  /** Additional class names */
  className?: string;
}

const radiusStyles = {
  none: "rounded-none",
  sm: "rounded-[var(--radius-sm)]",
  md: "rounded-[var(--radius-md)]",
  lg: "rounded-[var(--radius-lg)]",
  full: "rounded-full",
};

const variantStyles = {
  wave: "skeleton-wave",
  pulse: "skeleton-pulse",
  none: "",
};

export function Skeleton({
  width = "100%",
  height = "1rem",
  radius = "md",
  variant = "wave",
  className = "",
}: SkeletonProps) {
  return (
    <div
      className={`
        bg-[var(--color-canvas-subtle)]
        ${radiusStyles[radius]}
        ${variantStyles[variant]}
        ${className}
      `}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export interface SkeletonTextProps {
  /** Number of lines */
  lines?: number;
  /** Width of last line */
  lastLineWidth?: string;
  /** Additional class names */
  className?: string;
}

export function SkeletonText({ lines = 3, lastLineWidth = "60%", className = "" }: SkeletonTextProps) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          width={i === lines - 1 ? lastLineWidth : "100%"}
          height="1rem"
          radius="sm"
          variant="wave"
        />
      ))}
    </div>
  );
}

export interface SkeletonCardProps {
  /** Show header skeleton */
  header?: boolean;
  /** Number of content lines */
  lines?: number;
  /** Additional class names */
  className?: string;
}

export function SkeletonCard({ header = true, lines = 4, className = "" }: SkeletonCardProps) {
  return (
    <div className={`card-base space-y-4 ${className}`} aria-hidden="true">
      {header && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Skeleton width="40px" height="40px" radius="full" variant="wave" />
            <div className="space-y-2">
              <Skeleton width="60%" height="1rem" radius="sm" variant="wave" />
              <Skeleton width="40%" height="0.75rem" radius="sm" variant="wave" />
            </div>
          </div>
          <Skeleton width="80px" height="32px" radius="sm" variant="wave" />
        </div>
      )}
      <SkeletonText lines={lines} />
    </div>
  );
}

export interface SkeletonTableProps {
  /** Number of columns */
  columns: number;
  /** Number of rows */
  rows?: number;
  /** Show header */
  header?: boolean;
  /** Additional class names */
  className?: string;
}

export function SkeletonTable({ columns, rows = 5, header = true, className = "" }: SkeletonTableProps) {
  return (
    <div className={`table-container ${className}`} aria-hidden="true">
      <table className="table">
        {header && (
          <thead>
            <tr>
              {Array.from({ length: columns }).map((_, i) => (
                <th key={i} scope="col">
                  <Skeleton width="100%" height="1rem" radius="sm" variant="wave" />
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {Array.from({ length: rows }).map((_, rowIndex) => (
            <tr key={rowIndex}>
              {Array.from({ length: columns }).map((_, colIndex) => (
                <td key={colIndex}>
                  <Skeleton width="100%" height="1rem" radius="sm" variant="wave" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface SkeletonListProps {
  /** Number of items */
  items?: number;
  /** Show avatar */
  avatar?: boolean;
  /** Show action */
  action?: boolean;
  /** Additional class names */
  className?: string;
}

export function SkeletonList({ items = 5, avatar = true, action = false, className = "" }: SkeletonListProps) {
  return (
    <div className={`space-y-3 ${className}`} aria-hidden="true">
      {Array.from({ length: items }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          {avatar && <Skeleton width="40px" height="40px" radius="full" variant="wave" />}
          <div className="flex-1 space-y-2">
            <Skeleton width="60%" height="1rem" radius="sm" variant="wave" />
            <Skeleton width="40%" height="0.75rem" radius="sm" variant="wave" />
          </div>
          {action && <Skeleton width="80px" height="32px" radius="sm" variant="wave" />}
        </div>
      ))}
    </div>
  );
}

export interface SkeletonPageProps {
  /** Page title */
  title?: boolean;
  /** Stats row */
  stats?: boolean;
  /** Table skeleton */
  table?: { columns: number; rows?: number };
  /** List skeleton */
  list?: { items?: number; avatar?: boolean };
  /** Additional class names */
  className?: string;
}

export function SkeletonPage({ title = true, stats = false, table, list, className = "" }: SkeletonPageProps) {
  return (
    <div className={`space-y-6 ${className}`} aria-hidden="true">
      {title && (
        <div className="flex items-center justify-between">
          <Skeleton width="300px" height="2.5rem" radius="sm" variant="wave" />
          <Skeleton width="150px" height="32px" radius="sm" variant="wave" />
        </div>
      )}
      {stats && (
        <div className="flex flex-wrap gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} width="180px" height="100px" radius="md" variant="wave" />
          ))}
        </div>
      )}
      {table && <SkeletonTable columns={table.columns} rows={table.rows} />}
      {list && <SkeletonList items={list.items} avatar={list.avatar} />}
    </div>
  );
}