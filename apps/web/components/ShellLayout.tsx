"use client";

import React, { useEffect, useRef } from "react";
import { useShell } from "@/lib/useShell";
import { useShellLayout } from "@/hooks/useMediaQuery";
import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";
import { TopContextBar } from "@/components/TopContextBar";
import { CommandPalette } from "@/components/CommandPalette";
import { RightInspector } from "@/components/RightInspector";
import { NotificationContainer } from "@/components/Notification";
import { ClientErrorBoundary } from "@/components/ClientErrorBoundary";
import { SwitchWorkspaceDialog } from "@/components/workspace/SwitchWorkspaceDialog";

export interface ShellLayoutProps {
  children?: React.ReactNode;
}

export function ShellLayout({ children }: ShellLayoutProps) {
  const { state } = useShell();
  const { isSidebarDrawer, isInspectorDrawer } = useShellLayout();
  const { isNavCollapsed, inspectorOpen, inspectorMode, inspectorDockPosition } = state;
  const pathname = usePathname();

  const isInspectorVisible = Boolean(inspectorOpen && inspectorMode);
  /*
   * Chrome-less routes render the page on its own — no top bar, no sidebar,
   * no inspector.
   *
   * The workspace routes belong here because they are an *interstitial*
   * between signing in and working: the launcher's job is to pick an
   * incident, so wrapping it in the console's incident furniture (whose top
   * bar chip is bound to an active incident) would put "no incident" chrome
   * on the one page whose whole purpose is choosing one.
   */
  const isChromeLessRoute = pathname === "/login" || pathname.startsWith("/workspace");

  // Dynamic widths for CSS grid tracks:
  // Desktop:
  //   Sidebar: 240px (expanded) or 64px (collapsed - icon-only width)
  //   Inspector:
  //     - Docked to bottom (command center): 0px (does NOT shift or shrink the main body)
  //     - Docked to right sidebar: 360px (open) or 0px (closed)
  // Mobile/Tablet (isDrawer):
  //   Sidebar & Inspector are fixed overlay drawers and do not consume desktop grid columns
  const isRightInspector = isInspectorVisible && !isInspectorDrawer && inspectorDockPosition === "right";
  const sidebarWidthPx = isSidebarDrawer ? 0 : isNavCollapsed ? 64 : 240;
  const inspectorWidthPx = isRightInspector ? 360 : 0;

  // Track layout state changes to trigger window resize event for charts/graphs/timelines
  const prevCollapsedRef = useRef(isNavCollapsed);
  const prevInspectorRef = useRef(isRightInspector);
  const resizeTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (
      prevCollapsedRef.current !== isNavCollapsed ||
      prevInspectorRef.current !== isRightInspector
    ) {
      prevCollapsedRef.current = isNavCollapsed;
      prevInspectorRef.current = isRightInspector;

      if (resizeTimerRef.current) {
        clearTimeout(resizeTimerRef.current);
      }

      // Dispatch resize at completion of the 200ms transition so width-sensitive components re-measure
      resizeTimerRef.current = setTimeout(() => {
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("resize"));
          window.dispatchEvent(
            new CustomEvent("cauveris:layout-resize", {
              detail: { isNavCollapsed, inspectorOpen: isInspectorVisible, inspectorDockPosition },
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
  }, [isNavCollapsed, isRightInspector, isInspectorVisible, inspectorDockPosition]);

  return (
    <>
      {!isChromeLessRoute && <TopContextBar />}

      {/* Main Shell Grid - 3-Zone Dynamic Layout: Sidebar | Main Content | Contextual Inspector */}
      <div
        id="cauveris-shell-grid"
        data-sidebar-collapsed={isNavCollapsed}
        data-inspector-open={isInspectorVisible}
        data-inspector-dock={inspectorDockPosition || "bottom"}
        className={
          isChromeLessRoute
            ? pathname === "/login"
              ? "relative h-full w-full flex items-center justify-center bg-[var(--color-canvas)]"
              : "relative h-full w-full bg-[var(--color-canvas)]"
            : "relative h-full w-full lg:grid lg:grid-rows-[var(--shell-topbar-height)_1fr] transition-[grid-template-columns] duration-150 ease-out motion-reduce:transition-none"
        }
        style={
          isChromeLessRoute
            ? undefined
            : {
                "--shell-sidebar-current-width": `${sidebarWidthPx}px`,
                "--shell-inspector-current-width": `${inspectorWidthPx}px`,
                gridTemplateColumns: `var(--shell-sidebar-current-width) minmax(0, 1fr) var(--shell-inspector-current-width)`,
              } as React.CSSProperties
        }
      >
        {!isChromeLessRoute && (
          <>
            {/* Top Context Bar Spacer - Row 1, spans full width */}
            <div className="lg:col-span-full lg:row-span-1 pointer-events-none" aria-hidden="true" />

            {/* Left Sidebar Column - Row 2, Col 1 */}
            <div
              id="shell-sidebar-col"
              className="lg:row-start-2 lg:col-start-1 lg:row-span-1 relative transition-[width] duration-150 ease-out motion-reduce:transition-none overflow-visible"
              style={{ width: `${sidebarWidthPx}px` }}
            >
              <Sidebar />
            </div>

            {/* Main Content Area - Row 2, Col 2 (flexibly expands/contracts) */}
            <main
              id="main-content"
              className="relative min-w-0 w-full overflow-y-auto lg:row-start-2 lg:col-start-2 pt-[calc(var(--shell-topbar-height)+1rem)] lg:pt-5 pb-8 px-4 sm:px-6 lg:px-8 transition-all duration-150 ease-out motion-reduce:transition-none"
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

        {isChromeLessRoute && (
          <main
            id="main-content"
            className={
              pathname === "/login"
                ? "relative min-w-0 w-full overflow-y-auto flex items-center justify-center min-h-screen p-4"
                : "relative min-w-0 w-full min-h-screen flex flex-col"
            }
            role="main"
          >
            <ClientErrorBoundary>{children}</ClientErrorBoundary>
          </main>
        )}
      </div>

      {/* Global search palette — opened by clicking the search bar (no hotkey) */}
      <CommandPalette />

      {/* Switch Workspace confirmation dialog (asks to save session before leaving) */}
      {!isChromeLessRoute && <SwitchWorkspaceDialog />}

      {/* Notifications */}
      <NotificationContainer />
    </>
  );
}

export default ShellLayout;
