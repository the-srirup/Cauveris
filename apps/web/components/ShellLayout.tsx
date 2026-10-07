"use client";

import React, { useEffect, useRef } from "react";
import { useShell } from "@/lib/useShell";
import { useShellLayout } from "@/hooks/useMediaQuery";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { TopContextBar } from "@/components/TopContextBar";
import { RightInspector } from "@/components/RightInspector";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationContainer } from "@/components/Notification";
import { ClientErrorBoundary } from "@/components/ClientErrorBoundary";

export interface ShellLayoutProps {
  children?: React.ReactNode;
}

export function ShellLayout({ children }: ShellLayoutProps) {
  const { state, toggleNavCollapse } = useShell();
  const { isSidebarDrawer, isInspectorDrawer } = useShellLayout();
  const { isNavCollapsed, inspectorOpen, inspectorMode } = state;
  const pathname = usePathname();

  const isInspectorVisible = Boolean(inspectorOpen && inspectorMode);
  const isLoginPage = pathname === "/login";

  // Dynamic widths for CSS grid tracks:
  // Desktop:
  //   Sidebar: 240px (expanded) or 64px (collapsed)
  //   Inspector: 360px (open) or 0px (closed)
  // Mobile/Tablet (<lg / isDrawer):
  //   Sidebar & Inspector are fixed overlay drawers and do not consume desktop grid columns
  const sidebarWidthPx = isSidebarDrawer ? 0 : isNavCollapsed ? 64 : 240;
  const inspectorWidthPx = isInspectorDrawer || !isInspectorVisible ? 0 : 360;

  // Track layout state changes to trigger window resize event for charts/graphs/timelines
  const prevCollapsedRef = useRef(isNavCollapsed);
  const prevInspectorRef = useRef(isInspectorVisible);
  const resizeTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (
      prevCollapsedRef.current !== isNavCollapsed ||
      prevInspectorRef.current !== isInspectorVisible
    ) {
      prevCollapsedRef.current = isNavCollapsed;
      prevInspectorRef.current = isInspectorVisible;

      if (resizeTimerRef.current) {
        clearTimeout(resizeTimerRef.current);
      }

      // Dispatch resize at completion of the 200ms transition so width-sensitive components re-measure
      resizeTimerRef.current = setTimeout(() => {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("resize"));
          window.dispatchEvent(
            new CustomEvent("cauveris:layout-resize", {
              detail: { isNavCollapsed, inspectorOpen: isInspectorVisible },
            })
          );
        }
      }, 200);

      return () => {
        if (resizeTimerRef.current) {
          clearTimeout(resizeTimerRef.current);
        }
      };
    }
  }, [isNavCollapsed, isInspectorVisible]);

  // Keyboard shortcut: '[' toggles sidebar collapse when not typing in form inputs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "[" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const target = e.target as HTMLElement | null;
        const isInput =
          target &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.tagName === "SELECT" ||
            target.isContentEditable);
        if (!isInput) {
          e.preventDefault();
          toggleNavCollapse();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleNavCollapse]);

  return (
    <>
      {!isLoginPage && <TopContextBar />}

      {/* Main Shell Grid - 3-Zone Dynamic Layout: Sidebar | Main Content | Contextual Inspector */}
      <div
        id="cauveris-shell-grid"
        data-sidebar-collapsed={isNavCollapsed}
        data-inspector-open={isInspectorVisible}
        className={
          isLoginPage
            ? "relative h-full w-full flex items-center justify-center bg-[var(--theme-background)]"
            : "relative h-full w-full lg:grid lg:grid-rows-[48px_1fr_auto] transition-[grid-template-columns] duration-200 ease-out motion-reduce:transition-none"
        }
        style={
          isLoginPage
            ? undefined
            : {
                "--shell-sidebar-current-width": `${sidebarWidthPx}px`,
                "--shell-inspector-current-width": `${inspectorWidthPx}px`,
                gridTemplateColumns: `var(--shell-sidebar-current-width) minmax(0, 1fr) var(--shell-inspector-current-width)`,
              } as React.CSSProperties
        }
      >
        {!isLoginPage && (
          <>
            {/* Top Context Bar Spacer - Row 1, spans full width */}
            <div className="lg:col-span-full lg:row-span-1 pointer-events-none" aria-hidden="true" />

            {/* Left Sidebar Column - Row 2, Col 1 */}
            <div
              id="shell-sidebar-col"
              className="lg:row-start-2 lg:col-start-1 lg:row-span-1 relative transition-[width] duration-200 ease-out motion-reduce:transition-none overflow-visible"
              style={{ width: `${sidebarWidthPx}px` }}
            >
              <Sidebar />
            </div>

            {/* Main Content Area - Row 2, Col 2 (flexibly expands/contracts) */}
            <main
              id="main-content"
              className="relative min-w-0 w-full overflow-y-auto lg:row-start-2 lg:col-start-2 pt-[48px] lg:pt-0 pb-[32px] lg:pl-[var(--space-6)] lg:pr-[var(--space-6)] transition-all duration-200 ease-out motion-reduce:transition-none"
              role="main"
            >
              <ClientErrorBoundary>{children}</ClientErrorBoundary>
            </main>

            {/* Right Inspector Column - Row 2, Col 3 */}
            <div
              id="shell-inspector-col"
              className="lg:row-start-2 lg:col-start-3 lg:row-span-1 relative transition-[width] duration-200 ease-out motion-reduce:transition-none overflow-visible"
              style={{ width: `${inspectorWidthPx}px` }}
            >
              <RightInspector />
            </div>

                      </>
        )}

        {isLoginPage && (
          <main
            id="main-content"
            className="relative min-w-0 w-full overflow-y-auto flex items-center justify-center min-h-screen p-4"
            role="main"
          >
            <ClientErrorBoundary>{children}</ClientErrorBoundary>
          </main>
        )}
      </div>

      {/* Command Palette (overlay) */}
      <CommandPalette />

      {/* Notifications */}
      <NotificationContainer />
    </>
  );
}

export default ShellLayout;
