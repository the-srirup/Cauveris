"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, X, LayoutDashboard, Clock, GitBranch, Eye, FlaskConical, Wrench, RotateCcw, Database, FileText, Settings, Zap } from "lucide-react";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";
import type { NavItemKey } from "@/lib/useShell";
import { Badge } from "./ui";

const NAV = [
  { href: "/", label: "mission-control", icon: <LayoutDashboard className="h-4 w-4" />, group: "investigation" },
  { href: "/reality-rewind", label: "reality-rewind", icon: <Clock className="h-4 w-4" />, group: "investigation" },
  { href: "/causal-constellation", label: "causal-constellation", icon: <GitBranch className="h-4 w-4" />, group: "investigation" },
  { href: "/holographic-reconstruction", label: "holographic-reconstruction", icon: <Eye className="h-4 w-4" />, group: "analysis" },
  { href: "/ghost-lab", label: "ghost-lab", icon: <FlaskConical className="h-4 w-4" />, group: "analysis" },
  { href: "/patch-forge", label: "patch-forge", icon: <Wrench className="h-4 w-4" />, group: "analysis" },
  { href: "/victory-replay", label: "victory-replay", icon: <RotateCcw className="h-4 w-4" />, group: "operations" },
  { href: "/evidence-vault", label: "evidence-vault", icon: <Database className="h-4 w-4" />, group: "operations" },
  { href: "/reports", label: "reports", icon: <FileText className="h-4 w-4" />, group: "operations" },
  { href: "/settings", label: "settings", icon: <Settings className="h-4 w-4" />, group: "operations" },
] as const;

const GROUP_LABELS = {
  investigation: "Investigation",
  analysis: "Analysis",
  operations: "Operations",
} as const;

const GROUP_ICONS = {
  investigation: Zap,
  analysis: GitBranch,
  operations: Wrench,
} as const;

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
  }, {} as Record<string, Array<(typeof NAV)[number]>>);

  const collapsedWidth = "w-16"; // 64px
  const expandedWidth = "w-60"; // 240px

  return (
    <>
      {/* Mobile Overlay */}
      {state.isNavDrawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-[var(--color-canvas)]/80 lg:hidden"
          onClick={() => handleDrawerToggle(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-[var(--z-nav-sidebar)]
          flex flex-col
          bg-[var(--color-canvas-inset)]
          border-r border-[var(--color-border-default)]
          transition-all duration-200 ease-out motion-reduce:transition-none
          ${state.isNavCollapsed ? collapsedWidth : expandedWidth}
          ${state.isNavDrawerOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
        aria-label="Sidebar"
        data-collapsed={state.isNavCollapsed}
        data-drawer={state.isNavDrawerOpen}
      >
        {/* Brand Header */}
        <div className="flex items-center justify-between h-[var(--shell-topbar-height)] px-3 border-b border-[var(--color-border-default)]">
          {!state.isNavCollapsed && (
            <Link href="/" className="flex items-center gap-2 flex-1 min-w-0" aria-label="Cauveris Home">
              <div className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] bg-[var(--color-accent-muted)] ring-1 ring-[var(--color-accent-subtle)] flex-shrink-0">
                <svg className="h-4 w-4 text-[var(--color-accent-fg)]" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7Z" />
                </svg>
              </div>
              <div className="leading-tight min-w-0">
                <div className="text-sm font-semibold tracking-wide text-[var(--color-fg-default)] truncate">Cauveris</div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--color-fg-subtle)] truncate">Reality Debugger</div>
              </div>
            </Link>
          )}

          {/* Collapse/Drawer Toggle */}
          <div className="flex items-center gap-1">
            {state.isNavDrawerOpen && (
              <Tooltip content="Close sidebar" position="right">
                <button
                  onClick={() => handleDrawerToggle(false)}
                  className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors lg:hidden"
                  aria-label="Close sidebar"
                >
                  <X className="h-4 w-4" />
                </button>
              </Tooltip>
            )}
            <Tooltip content={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"} position={state.isNavCollapsed ? "right" : "bottom"}>
              <button
                onClick={toggleNavCollapse}
                className="flex h-8 w-8 items-center justify-center rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]"
                aria-label={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"}
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </Tooltip>
          </div>
        </div>

        {/* Mobile drawer close button (when open) */}
        {state.isNavDrawerOpen && !state.isNavCollapsed && (
          <div className="lg:hidden px-3 py-2">
            <button
              onClick={() => handleDrawerToggle(false)}
              className="flex items-center gap-2 w-full px-3 py-2 rounded-[var(--radius-md)] text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] hover:text-[var(--color-fg-default)] transition-colors"
            >
              <X className="h-4 w-4" />
              <span>Close Sidebar</span>
            </button>
          </div>
        )}

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Navigation sections">
          {Object.entries(groupedNav).map(([group, items]) => {
            const GroupIcon = GROUP_ICONS[group as keyof typeof GROUP_ICONS] || Zap;
            return (
              <div key={group} className="mb-4">
                {!state.isNavCollapsed && (
                  <div className="mb-2 px-3 text-[10px] font-medium uppercase tracking-widest text-[var(--color-fg-subtle)] flex items-center gap-1.5">
                    <GroupIcon className="h-3 w-3" aria-hidden="true" />
                    {GROUP_LABELS[group as keyof typeof GROUP_LABELS] || group}
                  </div>
                )}
              <ul className="space-y-0.5" role="list">
                {items.map((item) => {
                  const active = getActive(item.href);
                  const label = item.label.replace("-", " ");
                  return (
                    <li key={item.href}>
                      {state.isNavCollapsed ? (
                        <Tooltip content={label} position="right">
                          <Link
                            href={item.href}
                            className={`
                              relative flex items-center justify-center gap-3 rounded-[var(--radius-md)] px-2 py-2.5 text-sm font-medium
                              transition-colors duration-150 ease-out
                              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
                              ${active
                                ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)]"
                                : "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] hover:text-[var(--color-fg-default)]"
                              }
                            `}
                            aria-current={active ? "page" : undefined}
                            onClick={() => handleDrawerToggle(false)}
                          >
                            {active && (
                              <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-[var(--color-accent-fg)]" aria-hidden="true" />
                            )}
                            <span className="flex-shrink-0" aria-hidden="true">{item.icon}</span>
                          </Link>
                        </Tooltip>
                      ) : (
                        <Link
                          href={item.href}
                          className={`
                            relative flex items-center gap-3 rounded-[var(--radius-md)] px-3 py-2.5 text-sm font-medium
                            transition-colors duration-150 ease-out
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-canvas)]
                            ${active
                              ? "bg-[var(--color-accent-muted)] text-[var(--color-accent-fg)]"
                              : "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] hover:text-[var(--color-fg-default)]"
                            }
                          `}
                          aria-current={active ? "page" : undefined}
                          onClick={() => handleDrawerToggle(false)}
                        >
                          {active && (
                            <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-[var(--color-accent-fg)]" aria-hidden="true" />
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
          );
        })}

          {/* Footer status */}
          {!state.isNavCollapsed && (
            <div className="mt-auto border-t border-[var(--color-border-default)] pt-4 px-3">
              <div className="flex items-center gap-2 text-xs text-[var(--color-fg-muted)]">
                <Badge variant="success" dot size="sm" className="text-[10px]">
                  Systems Nominal
                </Badge>
              </div>
            </div>
          )}
        </nav>
      </aside>
    </>
  );
}