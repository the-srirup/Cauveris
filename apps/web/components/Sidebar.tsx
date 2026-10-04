"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { tv } from "tailwind-variants";
import { ChevronLeft, ChevronRight, Menu, X, LayoutDashboard, Clock, GitBranch, Eye, FlaskConical, Wrench, RotateCcw, Database, FileText, Settings } from "lucide-react";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import type { NavItemKey } from "@/lib/useShell";

const sidebarStyles = tv({
  base: `
    fixed inset-y-0 left-0 z-40 flex flex-col
    bg-[var(--theme-surface)]/80 backdrop-blur-xl border-r border-[var(--color-border)]
    transition-all duration-200 ease-out
    motion-reduce:transition-none
  `,
  variants: {
    collapsed: {
      true: "w-16 lg:w-16",
      false: "w-60 lg:w-60",
    },
    isDrawer: {
      true: "transform -translate-x-full lg:translate-x-0",
      false: "translate-x-0",
    },
  },
  defaultVariants: {
    collapsed: false,
    isDrawer: false,
  },
});

const navItemStyles = tv({
  base: `
    relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium
    transition-all duration-150 ease-out
    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]
  `,
  variants: {
    active: {
      true: "bg-[var(--color-accent)]/10 text-[var(--color-accent)]",
      false: "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)]",
    },
    collapsed: {
      true: "justify-center px-2",
      false: "justify-start px-3",
    },
  },
  defaultVariants: {
    active: false,
    collapsed: false,
  },
});

const NAV: { href: string; label: NavItemKey; icon: React.ReactNode; group: "investigation" | "analysis" | "operations" }[] = [
  { href: "/", label: "mission-control", icon: <LayoutDashboard className="h-5 w-5" />, group: "investigation" },
  { href: "/reality-rewind", label: "reality-rewind", icon: <Clock className="h-5 w-5" />, group: "investigation" },
  { href: "/causal-constellation", label: "causal-constellation", icon: <GitBranch className="h-5 w-5" />, group: "investigation" },
  { href: "/holographic-reconstruction", label: "holographic-reconstruction", icon: <Eye className="h-5 w-5" />, group: "analysis" },
  { href: "/ghost-lab", label: "ghost-lab", icon: <FlaskConical className="h-5 w-5" />, group: "analysis" },
  { href: "/patch-forge", label: "patch-forge", icon: <Wrench className="h-5 w-5" />, group: "analysis" },
  { href: "/victory-replay", label: "victory-replay", icon: <RotateCcw className="h-5 w-5" />, group: "operations" },
  { href: "/evidence-vault", label: "evidence-vault", icon: <Database className="h-5 w-5" />, group: "operations" },
  { href: "/reports", label: "reports", icon: <FileText className="h-5 w-5" />, group: "operations" },
  { href: "/settings", label: "settings", icon: <Settings className="h-5 w-5" />, group: "operations" },
];

const GROUP_LABELS = {
  investigation: "Investigation",
  analysis: "Analysis",
  operations: "Operations",
};

export default function Sidebar() {
  const pathname = usePathname();
  const { state, setNavDrawer, toggleNavCollapse } = useShell();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // Sync drawer state
  useEffect(() => {
    setIsDrawerOpen(state.isNavDrawerOpen);
  }, [state.isNavDrawerOpen]);

  const handleDrawerToggle = (open: boolean) => {
    setIsDrawerOpen(open);
    setNavDrawer(open);
  };

  // Determine active state
  const getActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname?.startsWith(href);
  };

  // Group nav items
  const groupedNav = NAV.reduce((acc, item) => {
    if (!acc[item.group]) acc[item.group] = [];
    acc[item.group].push(item);
    return acc;
  }, {} as Record<string, typeof NAV>);

  return (
    <>
      {/* Mobile Overlay */}
      {state.isNavDrawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-[var(--theme-background)]/50 lg:hidden"
          onClick={() => handleDrawerToggle(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={sidebarStyles({ collapsed: state.isNavCollapsed, isDrawer: state.isNavDrawerOpen })}
        aria-label="Sidebar"
        data-collapsed={state.isNavCollapsed}
      >
        {/* Brand Header */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-[var(--color-border)]">
          {!state.isNavCollapsed && (
            <Link href="/" className="flex items-center gap-3 flex-1 min-w-0" aria-label="Cauveris Home">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--color-accent)]/15 ring-1 ring-[var(--color-accent)]/30 flex-shrink-0">
                <svg className="h-5 w-5 text-[var(--color-brand-primary)]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7Z" />
                </svg>
              </div>
              <div className="leading-tight min-w-0">
                <div className="text-sm font-bold tracking-wide text-[var(--color-text-primary)] truncate">Cauveris</div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--color-text-muted)] truncate">Reality Debugger</div>
              </div>
            </Link>
          )}

          {/* Collapse/Drawer Toggle */}
          <div className="flex items-center gap-1">
            {state.isNavDrawerOpen && (
              <Tooltip content="Close sidebar" position="right">
                <button
                  onClick={() => handleDrawerToggle(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors lg:hidden"
                  aria-label="Close sidebar"
                >
                  <X className="h-4 w-4" />
                </button>
              </Tooltip>
            )}
            <Tooltip content={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"} position={state.isNavCollapsed ? "right" : "bottom"}>
              <button
                onClick={toggleNavCollapse}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-surface-2)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--theme-background)]"
                aria-label={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                {state.isNavCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
              </button>
            </Tooltip>
          </div>
        </div>

        {/* Mobile drawer close button (when open) */}
        {state.isNavDrawerOpen && !state.isNavCollapsed && (
          <div className="lg:hidden px-4 py-2">
            <button
              onClick={() => handleDrawerToggle(false)}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-lg text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-[var(--color-text-primary)] transition-colors"
            >
              <X className="h-4 w-4" />
              <span>Close Sidebar</span>
            </button>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Navigation sections">
          {Object.entries(groupedNav).map(([group, items]) => (
            <div key={group} className="mb-4">
              {!state.isNavCollapsed && (
                <div className="mb-2 px-3 text-[10px] font-medium uppercase tracking-widest text-[var(--color-text-muted)]">
                  {GROUP_LABELS[group as keyof typeof GROUP_LABELS] || group}
                </div>
              )}
              <ul className="space-y-1" role="list">
                {items.map((item) => {
                  const active = getActive(item.href);
                  const label = item.label.replace("-", " ");
                  return (
                    <li key={item.href}>
                      {state.isNavCollapsed ? (
                        <Tooltip content={label} position="right">
                          <Link
                            href={item.href}
                            className={navItemStyles({ active, collapsed: true })}
                            aria-current={active ? "page" : undefined}
                            onClick={() => handleDrawerToggle(false)}
                          >
                            {active && (
                              <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-[var(--color-accent)]" />
                            )}
                            <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                          </Link>
                        </Tooltip>
                      ) : (
                        <Link
                          href={item.href}
                          className={navItemStyles({ active, collapsed: false })}
                          aria-current={active ? "page" : undefined}
                          onClick={() => handleDrawerToggle(false)}
                        >
                          {active && (
                            <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-[var(--color-brand-primary)]" />
                          )}
                          <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                          <span className="truncate">{label}</span>
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}

          {/* Footer status */}
          {!state.isNavCollapsed && (
            <div className="mt-auto border-t border-[var(--color-border)] pt-4 px-3">
              <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--color-brand-success)] opacity-60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--color-brand-success)]" />
                </span>
                Systems Nominal
              </div>
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}