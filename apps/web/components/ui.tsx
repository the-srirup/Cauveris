import type { ReactNode } from "react";
import { Input } from "./primitives/Input";
import { Select } from "./primitives/Select";

export { Input, Select };
export * from "./Tooltip";

/* ---------- Card ---------- */
export function Card({
  title,
  icon,
  action,
  children,
  className = "",
  tone = "default",
}: {
  title?: string;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  tone?: "default" | "danger" | "success" | "accent";
}) {
  return (
    <section
      className={`glass ring-glow rounded-2xl border border-[var(--color-border)] p-[var(--card-padding)] ${className}`}
    >
      {(title || action) && (
        <header className="mb-5 flex items-center justify-between gap-4">
          <h2 className="flex items-center gap-2.5 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {icon && (
              <span className={tone === "accent" ? "text-[var(--color-accent)]/70" : "text-[var(--color-brand-primary)]/70"}>
                {icon}
              </span>
            )}
            {title}
          </h2>
          {action}
        </header>
      )}
      <div className="space-y-[var(--card-gap)]">
        {children}
      </div>
    </section>
  );
}

export function CardHeader({ children, className = "", ...props }: { children: ReactNode; className?: string } & Record<string, any>) {
  return <div className={`mb-4 ${className}`} {...props}>{children}</div>;
}

export function CardTitle({ children, className = "", ...props }: { children: ReactNode; className?: string } & Record<string, any>) {
  return <h3 className={`text-lg font-semibold text-[var(--color-text-primary)] ${className}`} {...props}>{children}</h3>;
}

export function CardDescription({ children, className = "", ...props }: { children: ReactNode; className?: string } & Record<string, any>) {
  return <p className={`text-sm text-[var(--color-text-muted)] ${className}`} {...props}>{children}</p>;
}

export function CardContent({ children, className = "", ...props }: { children: ReactNode; className?: string } & Record<string, any>) {
  return <div className={className} {...props}>{children}</div>;
}

/* ---------- Badge ---------- */
export function Badge({
  children,
  tone = "neutral",
  dot = false,
  className = "",
}: {
  children: ReactNode;
  tone?: "neutral" | "primary" | "success" | "danger" | "amber" | "secondary" | "muted" | "accent";
  dot?: boolean;
  className?: string;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] ring-[var(--color-border)]",
    primary: "bg-[var(--color-brand-primary)]/10 text-[var(--color-brand-primary)] ring-[var(--color-brand-primary)]/25",
    success: "bg-[var(--color-brand-success)]/10 text-[var(--color-brand-success)] ring-[var(--color-brand-success)]/25",
    danger: "bg-[var(--color-brand-danger)]/10 text-[var(--color-brand-danger)] ring-[var(--color-brand-danger)]/25",
    amber: "bg-[var(--color-brand-warning)]/10 text-[var(--color-brand-warning)] ring-[var(--color-brand-warning)]/25",
    secondary: "bg-[var(--color-brand-warning)]/10 text-[var(--color-brand-warning)] ring-[var(--color-brand-warning)]/25",
    muted: "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] ring-[var(--color-border)]",
    accent: "bg-[var(--color-accent)]/10 text-[var(--color-accent)] ring-[var(--color-accent)]/25",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${tones[tone]} ${className}`}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            tone === "success"
              ? "bg-[var(--color-brand-success)]"
              : tone === "danger"
                ? "bg-[var(--color-brand-danger)]"
                : tone === "amber" || tone === "secondary"
                  ? "bg-[var(--color-brand-warning)]"
                  : tone === "accent"
                    ? "bg-[var(--color-accent)]"
                    : "bg-[var(--color-brand-primary)]"
          }`}
        />
      )}
      {children}
    </span>
  );
}

/* ---------- Stat ---------- */
export function Stat({
  label,
  value,
  sub,
  trend,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  trend?: "up" | "down" | "flat" | "success" | "danger" | "warning" | "secondary" | "muted";
}) {
  const trendColor =
    trend === "up" || trend === "success"
      ? "text-[var(--color-brand-success)]"
      : trend === "down" || trend === "danger"
        ? "text-[var(--color-brand-danger)]"
        : trend === "warning" || trend === "secondary"
          ? "text-[var(--color-brand-warning)]"
          : "text-[var(--color-text-muted)]";
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/60 p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-2xl font-semibold text-[var(--color-text-primary)]">
        {value}
      </div>
      {sub && <div className={`mt-1 text-xs ${trendColor}`}>{sub}</div>}
    </div>
  );
}

/* ---------- Progress ---------- */
export function Progress({
  value,
  tone = "primary",
  className = "",
}: {
  value: number;
  tone?: "primary" | "success" | "danger" | "amber" | "secondary" | "accent";
  className?: string;
}) {
  const bar =
    tone === "success"
      ? "bg-[var(--color-brand-success)]"
      : tone === "danger"
        ? "bg-[var(--color-brand-danger)]"
        : tone === "amber" || tone === "secondary"
          ? "bg-[var(--color-brand-warning)]"
          : tone === "accent"
            ? "bg-[var(--color-accent)]"
            : "bg-[var(--color-brand-primary)]";
  return (
    <div
      className={`h-2 w-full overflow-hidden rounded-full bg-[var(--color-surface-2)] ${className}`}
    >
      <div
        className={`h-full rounded-full ${bar} transition-all duration-500`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

/* ---------- Button ---------- */
export function Button({
  children,
  variant = "primary",
  size = "md",
  className = "",
  title,
  onClick,
  disabled = false,
  type = "button",
  "aria-label": ariaLabel,
  ...props
}: {
  children: ReactNode;
  variant?: "primary" | "outline" | "danger" | "ghost" | "success" | "secondary";
  size?: "sm" | "md" | "lg";
  className?: string;
  title?: string;
  onClick?: (e?: any) => void;
  disabled?: boolean;
  type?: "button" | "submit" | "reset";
  "aria-label"?: string;
} & Record<string, any>) {
  const sizeClasses =
    size === "sm"
      ? "h-8 px-3 text-xs gap-1.5 rounded-lg"
      : size === "lg"
        ? "h-11 px-5 text-sm gap-2.5 rounded-xl"
        : "h-9 px-4 text-sm gap-2 rounded-lg";
  const styles: Record<string, string> = {
    primary: disabled
      ? "bg-[var(--color-accent)]/40 text-white/50 cursor-not-allowed border-[var(--color-accent)]/20"
      : "bg-[var(--color-accent)] text-white font-medium shadow-sm shadow-[var(--color-accent)]/25 hover:opacity-90 active:opacity-70 border-[var(--color-accent)]/40",
    outline: disabled
      ? "border border-[var(--color-border)] text-[var(--color-text-muted)]/40 cursor-not-allowed bg-transparent"
      : "border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]/80 hover:border-[var(--color-border-strong)] active:bg-[var(--color-surface-2)]/60",
    secondary: disabled
      ? "border border-[var(--color-border)] text-[var(--color-text-muted)]/40 cursor-not-allowed bg-[var(--color-surface-2)]/40"
      : "border border-[var(--color-border)] bg-[var(--color-surface-2)] text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)]/80 hover:border-[var(--color-border-strong)] active:bg-[var(--color-surface-2)]/60",
    danger: disabled
      ? "bg-[var(--color-brand-danger)]/40 text-white/50 cursor-not-allowed border border-[var(--color-brand-danger)]/20"
      : "bg-[var(--color-brand-danger)] text-white font-medium shadow-sm hover:bg-[var(--color-brand-danger)]/90 active:bg-[var(--color-brand-danger)]/80 border border-[var(--color-brand-danger)]/40",
    success: disabled
      ? "bg-[var(--color-brand-success)]/40 text-white/50 cursor-not-allowed border border-[var(--color-brand-success)]/20"
      : "bg-[var(--color-brand-success)] text-white font-medium shadow-sm hover:bg-[var(--color-brand-success)]/90 active:bg-[var(--color-brand-success)]/80 border border-[var(--color-brand-success)]/40",
    ghost: disabled
      ? "text-[var(--color-text-muted)]/40 cursor-not-allowed"
      : "text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] active:bg-[var(--color-surface-2)]",
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      aria-disabled={disabled}
      aria-label={ariaLabel}
      title={title}
      className={`inline-flex items-center justify-center font-medium leading-none whitespace-nowrap select-none transition-all duration-150 active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)] ${sizeClasses} ${styles[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}

/* ---------- Page header ---------- */
export function PageHeader({
  title,
  subtitle,
  badge,
}: {
  title: string;
  subtitle?: string;
  badge?: ReactNode;
}) {
  return (
    <div className="mb-[var(--space-8)]">
      <div className="flex items-center gap-3">
        <h1 className="text-gradient text-3xl font-bold tracking-tight">
          {title}
        </h1>
        {badge}
      </div>
      {subtitle && <p className="mt-[var(--space-1)] text-sm text-[var(--color-text-muted)]">{subtitle}</p>}
    </div>
  );
}

/* ---------- K/V row ---------- */
export function KV({
  label,
  value,
  sub,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-[var(--space-2)] text-sm">
      <div>
        <span className="text-[var(--color-text-muted)]">{label}</span>
        {sub && <span className="block text-sm text-[var(--color-text-muted)]/70">{sub}</span>}
      </div>
      <span className="text-right font-medium text-[var(--color-text-primary)]">{value}</span>
    </div>
  );
}

/* ---------- Toggle (Premium) ---------- */
export function Toggle({
  checked,
  onChange,
  disabled = false,
  className = "",
  size = "md",
  "aria-label": ariaLabel,
  ...props
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
  size?: "sm" | "md" | "lg";
  "aria-label"?: string;
} & Record<string, any>) {
  const sizeClasses = {
    sm: "h-5 w-9",
    md: "h-6 w-11",
    lg: "h-7 w-13",
  };
  const thumbSizes = {
    sm: "h-3.5 w-3.5",
    md: "h-4 w-4",
    lg: "h-5 w-5",
  };
  const thumbTranslate = {
    sm: { checked: "translate-x-4", unchecked: "translate-x-0.5" },
    md: { checked: "translate-x-6", unchecked: "translate-x-1" },
    lg: { checked: "translate-x-7", unchecked: "translate-x-1" },
  };

  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      className={`
        relative inline-flex items-center justify-between flex-shrink-0 cursor-pointer rounded-full border-2 transition-all duration-200 ease-out
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
        active:scale-[0.98]
        ${disabled ? "opacity-50 cursor-not-allowed" : "hover:shadow-lg"}
        ${checked
          ? "bg-[var(--color-accent)]/30 border-[var(--color-accent)]/50 shadow-[0_0_0_1px_var(--color-accent)_0.3,_0_4px_12px_var(--color-accent)_0.2]"
          : "bg-[var(--color-surface-2)] border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/80 hover:border-[var(--color-border-strong)]"
        }
        ${sizeClasses[size]} ${className}
      `}
      style={{
        WebkitTapHighlightColor: 'transparent',
      }}
      {...props}
    >
      {/* Track glow effect when checked */}
      {checked && (
        <div className="absolute inset-0 rounded-full bg-[var(--color-accent)]/20 opacity-0 transition-opacity duration-200 peer-checked:opacity-100" aria-hidden="true" />
      )}

      {/* Thumb */}
      <span
        className={`
          relative inline-flex items-center justify-center
          rounded-full bg-[var(--color-text-primary)] shadow-[0_2px_4px_rgba(0,0,0,0.3),_0_0_0_1px_rgba(0,0,0,0.1)]
          transition-all duration-200 [transition-timing-function:cubic-bezier(0.34,1.56,0.64,1.1)]
          ${thumbSizes[size]}
          ${checked ? thumbTranslate[size].checked : thumbTranslate[size].unchecked}
          ${disabled ? "opacity-60" : ""}
        `}
        aria-hidden="true"
      >
        {/* Inner dot for checked state */}
        {checked && (
          <span className="relative h-1.5 w-1.5 rounded-full bg-[var(--color-accent)]/80" aria-hidden="true" />
        )}
      </span>
    </button>
  );
}

/* ---------- Divider ---------- */
export function Divider({
  orientation = "horizontal",
  className = "",
}: {
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  return orientation === "horizontal" ? (
    <hr className={`border-t border-[var(--color-border)] ${className}`} role="separator" />
  ) : (
    <div className={`border-l border-[var(--color-border)] ${className}`} role="separator" />
  );
}