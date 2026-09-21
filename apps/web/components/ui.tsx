import type { ReactNode } from "react";

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
  const toneRing =
    tone === "danger"
      ? "border-danger/25"
      : tone === "success"
        ? "border-success/25"
        : tone === "accent"
          ? "border-primary/25"
          : "border-white/5";
  return (
    <section
      className={`glass ring-glow rounded-2xl border ${toneRing} p-6 ${className}`}
    >
      {(title || action) && (
        <header className="mb-5 flex items-center justify-between gap-4">
          <h2 className="flex items-center gap-2.5 text-sm font-semibold uppercase tracking-wide text-muted">
            {icon && (
              <span className="text-primary/70">{icon}</span>
            )}
            {title}
          </h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

/* ---------- Badge ---------- */
export function Badge({
  children,
  tone = "neutral",
  dot = false,
}: {
  children: ReactNode;
  tone?: "neutral" | "primary" | "success" | "danger" | "amber";
  dot?: boolean;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-white/5 text-muted",
    primary: "bg-primary/10 text-primary ring-primary/25",
    success: "bg-success/10 text-success ring-success/25",
    danger: "bg-danger/10 text-danger ring-danger/25",
    amber: "bg-secondary/10 text-secondary ring-secondary/25",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ${tones[tone]}`}
    >
      {dot && (
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            tone === "success"
              ? "bg-success"
              : tone === "danger"
                ? "bg-danger"
                : tone === "amber"
                  ? "bg-secondary"
                  : "bg-primary"
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
  trend?: "up" | "down" | "flat";
}) {
  const trendColor =
    trend === "up" ? "text-success" : trend === "down" ? "text-danger" : "text-muted";
  return (
    <div className="rounded-xl border border-white/5 bg-surface/40 p-4">
      <div className="text-[11px] font-medium uppercase tracking-wider text-muted">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-2xl font-semibold text-white">
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
  tone?: "primary" | "success" | "danger" | "amber";
  className?: string;
}) {
  const bar =
    tone === "success"
      ? "bg-success"
      : tone === "danger"
        ? "bg-danger"
        : tone === "amber"
          ? "bg-secondary"
          : "bg-primary";
  return (
    <div
      className={`h-2 w-full overflow-hidden rounded-full bg-white/5 ${className}`}
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
  className = "",
  onClick,
}: {
  children: ReactNode;
  variant?: "primary" | "outline" | "danger" | "ghost";
  className?: string;
  onClick?: () => void;
}) {
  const styles: Record<string, string> = {
    primary:
      "bg-primary text-background font-semibold shadow-lg shadow-primary/20 hover:bg-primary/90",
    outline:
      "border border-white/15 text-foreground hover:border-primary/50 hover:text-primary",
    danger: "bg-danger text-white font-semibold hover:bg-danger/90",
    ghost: "text-muted hover:bg-white/5 hover:text-white",
  };
  return (
    <button
      onClick={onClick}
      className={`rounded-xl px-5 py-2.5 text-sm transition-all active:scale-[0.97] ${styles[variant]} ${className}`}
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
    <div className="mb-8">
      <div className="flex items-center gap-3">
        <h1 className="text-gradient text-3xl font-bold tracking-tight">
          {title}
        </h1>
        {badge}
      </div>
      {subtitle && <p className="mt-1.5 text-sm text-muted">{subtitle}</p>}
    </div>
  );
}

/* ---------- K/V row ---------- */
export function KV({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium text-white">{value}</span>
    </div>
  );
}