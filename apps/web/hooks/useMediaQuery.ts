"use client";

import { useState, useEffect, useMemo } from "react";

/**
 * Breakpoint values matching the design requirements:
 * - 1366×768 (laptop)
 * - 1440×900 (laptop large)
 * - 1920×1080 (desktop)
 * - Tablet (~768-1023)
 * - Mobile (<768)
 */

export type Breakpoint = "mobile" | "tablet" | "laptop" | "desktop" | "widescreen";

const breakpoints = {
  mobile: 0,
  tablet: 768,
  laptop: 1024,
  desktop: 1440,
  widescreen: 1920,
} as const;

const mediaQueries = {
  mobile: `(max-width: ${breakpoints.tablet - 1}px)`,
  tablet: `(min-width: ${breakpoints.tablet}px) and (max-width: ${breakpoints.laptop - 1}px)`,
  laptop: `(min-width: ${breakpoints.laptop}px) and (max-width: ${breakpoints.desktop - 1}px)`,
  desktop: `(min-width: ${breakpoints.desktop}px) and (max-width: ${breakpoints.widescreen - 1}px)`,
  widescreen: `(min-width: ${breakpoints.widescreen}px)`,
  // Combined
  "tablet-down": `(max-width: ${breakpoints.laptop - 1}px)`,
  "desktop-up": `(min-width: ${breakpoints.laptop}px)`,
  "mobile-only": `(max-width: ${breakpoints.tablet - 1}px)`,
} as const;

export function useMediaQuery(query: keyof typeof mediaQueries): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mql = window.matchMedia(mediaQueries[query]);
    setMatches(mql.matches);

    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener?.("change", handler);
    return () => mql.removeEventListener?.("change", handler);
  }, [query]);

  return matches;
}

export function useBreakpoint(): Breakpoint {
  const isMobile = useMediaQuery("mobile-only");
  const isTablet = useMediaQuery("tablet");
  const isLaptop = useMediaQuery("laptop");
  const isDesktop = useMediaQuery("desktop");
  const isWidescreen = useMediaQuery("widescreen");

  if (isWidescreen) return "widescreen";
  if (isDesktop) return "desktop";
  if (isLaptop) return "laptop";
  if (isTablet) return "tablet";
  return "mobile";
}

export function useViewport() {
  const [width, setWidth] = useState(0);
  const [height, setHeight] = useState(0);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const update = () => {
      setWidth(window.innerWidth);
      setHeight(window.innerHeight);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  return { width, height };
}

/* -------------------------------------------------------------------------- */
/* Layout Helpers                                                             */
/* -------------------------------------------------------------------------- */

export function useShellLayout() {
  const breakpoint = useBreakpoint();
  const { width } = useViewport();

  const sidebarWidth = useMemo(() => {
    switch (breakpoint) {
      case "widescreen":
      case "desktop":
      case "laptop":
        return 240; // expanded
      case "tablet":
        return 64; // collapsed (icons only)
      case "mobile":
      default:
        return 0; // drawer
    }
  }, [breakpoint]);

  const isSidebarDrawer = breakpoint === "mobile" || breakpoint === "tablet";
  const isInspectorDrawer = breakpoint === "mobile" || breakpoint === "tablet";

  const inspectorWidth = useMemo(() => {
    if (isInspectorDrawer) return "100%";
    if (breakpoint === "laptop") return 320;
    return 360;
  }, [breakpoint, isInspectorDrawer]);

  const trayHeight = useMemo(() => {
    if (breakpoint === "mobile") return 48; // handle only
    if (breakpoint === "tablet") return 80; // compact
    return 200; // expanded
  }, [breakpoint]);

  return useMemo(
    () => ({
      breakpoint,
      width,
      sidebarWidth,
      isSidebarDrawer,
      isInspectorDrawer,
      inspectorWidth,
      trayHeight,
      // CSS class helpers
      sidebarClass: `fixed inset-y-0 left-0 z-40 transition-transform duration-200 ease-out ${
        isSidebarDrawer
          ? "transform translate-x-[-100%] lg:translate-x-0"
          : "translate-x-0"
      } w-[${sidebarWidth}px]`,
      mainClass: `flex-1 transition-all duration-200 ease-out ${
        !isSidebarDrawer ? `lg:pl-[${sidebarWidth}px]` : "pl-0"
      }`,
      inspectorClass: `fixed inset-y-0 right-0 z-30 transition-transform duration-200 ease-out ${
        isInspectorDrawer
          ? "transform translate-x-full lg:translate-x-0"
          : "translate-x-0"
      } w-[${inspectorWidth}]`,
      trayClass: `fixed bottom-0 left-0 right-0 z-20 transition-all duration-300 ease-out ${
        isSidebarDrawer ? "left-0" : "lg:left-[240px]"
      }`,
    }),
    [
      breakpoint,
      width,
      sidebarWidth,
      isSidebarDrawer,
      isInspectorDrawer,
      inspectorWidth,
      trayHeight,
    ]
  );
}