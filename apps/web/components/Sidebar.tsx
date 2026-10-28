"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChevronRight,
  ChevronLeft,
  X,
  LayoutDashboard,
  Clock,
  GitBranch,
  Eye,
  FlaskConical,
  Wrench,
  RotateCcw,
  Database,
  FileText,
  Settings,
} from "lucide-react";
import { Tooltip } from "./Tooltip";
import { useShell } from "@/lib/useShell";

export interface NavItem {
  href: string;
  label: string;
  altLabel?: string;
  icon: React.ComponentType<{ className?: string }>;
}

export interface NavSection {
  title: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    title: "Investigation",
    items: [
      { href: "/", label: "Overview", altLabel: "Mission Control", icon: LayoutDashboard },
      { href: "/reality-rewind", label: "Timeline", altLabel: "Reality Rewind", icon: Clock },
      { href: "/causal-constellation", label: "Hypotheses", altLabel: "Causal Constellation", icon: GitBranch },
    ],
  },
  {
    title: "Analysis",
    items: [
      { href: "/holographic-reconstruction", label: "Digital Twin", altLabel: "Holographic Reconstruction", icon: Eye },
      { href: "/ghost-lab", label: "Experiments", altLabel: "Ghost Lab", icon: FlaskConical },
      { href: "/patch-forge", label: "Patch", altLabel: "Patch Forge", icon: Wrench },
    ],
  },
  {
    title: "Operations",
    items: [
      { href: "/victory-replay", label: "Verification", altLabel: "Victory Replay", icon: RotateCcw },
      { href: "/evidence-vault", label: "Evidence", altLabel: "Evidence Vault", icon: Database },
      { href: "/reports", label: "Reports", altLabel: "Dossier Reports", icon: FileText },
      { href: "/settings", label: "System Status", altLabel: "Settings", icon: Settings },
    ],
  },
];

export const MAIN_NAV: NavItem[] = NAV_SECTIONS.flatMap((s) => s.items);

export default function Sidebar() {
  const pathname = usePathname();
  const { state, setNavDrawer, toggleNavCollapse } = useShell();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    setIsDrawerOpen(state.isNavDrawerOpen);
  }, [state.isNavDrawerOpen]);

  const handleDrawerToggle = (open: boolean) => {
    setIsDrawerOpen(open);
    setNavDrawer(open);
  };

  const isNavActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname?.startsWith(href);
  };

  const collapsedWidth = "w-16"; // 64px
  const expandedWidth = "w-60"; // 240px

  return (
    <>
      {/* Mobile Drawer Backdrop */}
      {state.isNavDrawerOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
          onClick={() => handleDrawerToggle(false)}
          aria-hidden="true"
        />
      )}

      {/* Main Sidebar */}
      <aside
        className={`
          fixed inset-y-0 left-0 z-[var(--z-nav-sidebar)]
          flex flex-col
          bg-[var(--color-canvas-inset)]
          border-r border-[var(--color-border-default)]
          transition-all duration-150 ease-out motion-reduce:transition-none
          select-none font-sans
          ${state.isNavCollapsed ? collapsedWidth : expandedWidth}
          ${state.isNavDrawerOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}
        `}
        aria-label="Sidebar"
        data-collapsed={state.isNavCollapsed}
        data-drawer={state.isNavDrawerOpen}
      >
        {/* Brand / Logo Header */}
        <div className="flex items-center justify-between h-[var(--topbar-height,54px)] px-3 border-b border-[var(--color-border-default)] bg-[var(--color-canvas-inset)]">
          {!state.isNavCollapsed && (
            <Link href="/" className="flex items-center gap-2.5 min-w-0" aria-label="Cauveris Home">
              <div className="flex h-7 w-7 items-center justify-center rounded-[var(--radius-sm,4px)] bg-[var(--color-accent)] text-white shrink-0 shadow-xs">
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2} viewBox="0 0 24 24" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7Z" />
                </svg>
              </div>
              <div className="leading-tight min-w-0">
                <span className="text-sm font-semibold tracking-tight text-[var(--color-fg-default)] block truncate">
                  Cauveris
                </span>
                <span className="text-xs text-[var(--color-fg-muted)] block truncate">
                  Incident Engineering
                </span>
                <span className="sr-only">Reality Debugger</span>
              </div>
            </Link>
          )}

          {/* Collapse/Expand Toggle */}
          <Tooltip content={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"} position="bottom">
            <button
              onClick={toggleNavCollapse}
              className="p-1.5 rounded-[var(--radius-sm,4px)] text-[var(--color-fg-muted)] hover:text-[var(--color-fg-default)] hover:bg-[var(--color-canvas-subtle)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]"
              aria-label={state.isNavCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {state.isNavCollapsed ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </button>
          </Tooltip>
        </div>

        {/* Mobile Drawer Close */}
        {state.isNavDrawerOpen && (
          <div className="p-2 border-b border-[var(--color-border-default)] lg:hidden">
            <button
              onClick={() => handleDrawerToggle(false)}
              className="w-full flex items-center justify-center gap-2 p-1.5 text-xs text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] rounded-[var(--radius-sm,4px)] transition-colors"
            >
              <X className="h-4 w-4" />
              <span>Close menu</span>
            </button>
          </div>
        )}

        {/* Navigation Links grouped by section */}
        <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-3" aria-label="Navigation sections">
          {NAV_SECTIONS.map((section) => (
            <div key={section.title} className="space-y-1">
              {!state.isNavCollapsed && (
                <div className="px-2.5 text-xs font-semibold text-[var(--color-fg-muted)] uppercase tracking-wider">
                  {section.title}
                </div>
              )}
              <ul className="space-y-0.5" role="list">
                {section.items.map((item) => {
                  const active = isNavActive(item.href);
                  const Icon = item.icon;

                  return (
                    <li key={item.href}>
                      {state.isNavCollapsed ? (
                        <Tooltip content={item.label} position="right">
                          <Link
                            href={item.href}
                            className={`
                              flex items-center justify-center h-8.5 w-full rounded-[var(--radius-sm,4px)]
                              transition-colors duration-100 ease-out
                              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]
                              ${
                                active
                                  ? "bg-[var(--color-canvas-subtle)] text-[var(--color-accent)] font-semibold border-l-2 border-[var(--color-accent)]"
                                  : "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] hover:text-[var(--color-fg-default)]"
                              }
                            `}
                            aria-current={active ? "page" : undefined}
                            onClick={() => handleDrawerToggle(false)}
                          >
                            <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                          </Link>
                        </Tooltip>
                      ) : (
                        <Link
                          href={item.href}
                          aria-label={item.altLabel ? `${item.label} (${item.altLabel})` : item.label}
                          className={`
                            flex items-center gap-2.5 h-8.5 px-2.5 rounded-[var(--radius-sm,4px)] text-sm font-medium
                            transition-colors duration-100 ease-out
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]
                            ${
                              active
                                ? "bg-[var(--color-canvas-subtle)] text-[var(--color-accent)] font-semibold border-l-2 border-[var(--color-accent)] pl-2"
                                : "text-[var(--color-fg-muted)] hover:bg-[var(--color-canvas-subtle)] hover:text-[var(--color-fg-default)]"
                            }
                          `}
                          aria-current={active ? "page" : undefined}
                          onClick={() => handleDrawerToggle(false)}
                        >
                          <Icon className={`h-4 w-4 shrink-0 ${active ? "text-[var(--color-accent)]" : "text-[var(--color-fg-muted)]"}`} aria-hidden="true" />
                          <span className="truncate">{item.label}</span>
                        </Link>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Footer Status */}
        {!state.isNavCollapsed && (
          <div className="border-t border-[var(--color-border-default)] p-3 bg-[var(--color-canvas-subtle)]/40">
            <div className="flex items-center justify-between text-xs text-[var(--color-fg-muted)]">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-[var(--color-success-emphasis,#1a7f37)] shrink-0" />
                <span className="text-xs">Systems Nominal</span>
              </div>
              <span className="text-xs font-mono text-[var(--color-fg-subtle)]">v2.4.0</span>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
