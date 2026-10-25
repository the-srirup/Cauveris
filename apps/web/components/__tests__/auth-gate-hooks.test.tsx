/**
 * Regression test: the pages must not violate the Rules of Hooks.
 *
 * Every page used to gate rendering on the auth store with an early return
 * placed *before* its remaining hooks:
 *
 *     const { isAuthenticated, isLoading } = useAuthStore();
 *     if (isLoading) return <Loading />;   // <-- early return
 *     if (!isAuthenticated) return <Redirecting />;
 *     const [x, setX] = useState(...);      // <-- hooks that never ran on the
 *                                            //     first render
 *
 * The auth store starts with `isLoading === true`, so the first render called
 * fewer hooks than the second one. React then throws
 * "Rendered more hooks than during the previous render." and the page
 * crashes for every signed-in user.
 *
 * The existing test-suite mocks the auth store with `isLoading: false`, so
 * the transition was never exercised. This test drives the transition.
 */
import { render, screen, act } from "@testing-library/react";
import React, { useEffect, useState } from "react";

const authMock = vi.hoisted(() => {
  const state = { isAuthenticated: false, isLoading: true };
  const listeners = new Set<() => void>();
  return { state, listeners };
});

vi.mock("@/lib/auth", () => ({
  useAuthStore: () => {
    const [, force] = useState(0);
    useEffect(() => {
      const listener = () => force((n) => n + 1);
      authMock.listeners.add(listener);
      return () => {
        authMock.listeners.delete(listener);
      };
    }, []);
    return authMock.state;
  },
  useAuthStore_zz: undefined,
  getAuthHeader: () => null,
}));

vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/"),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className = "",
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} className={className} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/useShell", () => ({
  useShell: () => ({
    state: {
      activeNav: "mission-control",
      isNavCollapsed: false,
      isNavDrawerOpen: false,
      incidentContext: {
        id: "CAU-0001",
        title: "Test Incident",
        state: "IDLE",
        pipelineStage: "IDLE",
        evidenceCoverage: 75,
        modelProvider: "Local Fixtures",
        backendStatus: "online",
        processingMode: "autonomous",
        isDemonstration: false,
      },
      inspectorOpen: false,
      inspectorMode: null,
      inspectorData: { mode: null },
      trayState: "compact",
      activities: [],
      commandPaletteOpen: false,
    },
    setActiveNav: vi.fn(),
    toggleNavCollapse: vi.fn(),
    setNavDrawer: vi.fn(),
    setIncidentContext: vi.fn(),
    openInspector: vi.fn(),
    closeInspector: vi.fn(),
    setTrayState: vi.fn(),
    addActivity: vi.fn(),
    removeActivity: vi.fn(),
    clearActivities: vi.fn(),
    toggleCommandPalette: vi.fn(),
    setCommandPalette: vi.fn(),
  }),
  buildIncidentContext: vi.fn(() => ({})),
  ShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/useIncident", () => ({
  useActiveIncident: () => ({
    incident: { id: "CAU-0001", title: "Test Incident" },
    incidentId: "CAU-0001",
    judgeMode: false,
    engineerMode: false,
    setIncidentId: vi.fn(),
    loadIncident: vi.fn(),
  }),
  buildIncidentContext: vi.fn(),
}));

// A permissive API stub: every method resolves to an empty object so the
// page's effects can run without a backend.
vi.mock("@/lib/api", () => {
  const handler: ProxyHandler<Record<string, unknown>> = {
    get(_target, prop: string) {
      if (prop === "then") return undefined;
      return vi.fn().mockResolvedValue({});
    },
  };
  const api = new Proxy({}, handler);
  return {
    api,
    Incident: undefined,
    PipelineStageInfo: undefined,
    PipelineEventsResponse: undefined,
    EvidenceValidationSummary: undefined,
    SystemHealthResponse: undefined,
    ModelProviderHealthResponse: undefined,
    StatusCenterResponse: undefined,
  };
});

vi.mock("@/components/Notification", () => ({
  notify: vi.fn(),
  NotificationContainer: () => null,
}));

vi.mock("@/hooks/useMediaQuery", () => ({
  useShellLayout: () => ({
    isSidebarDrawer: false,
    isInspectorDrawer: false,
    isMobile: false,
    isTablet: false,
    isLaptop: false,
    isDesktop: true,
  }),
  useMediaQuery: () => false,
}));

vi.mock("@/hooks/useKeyboardShortcut", () => ({
  useKeyboardShortcuts: vi.fn(),
}));

// The holographic page renders a WebGL canvas; jsdom has no WebGL context.
vi.mock("@react-three/fiber", () => ({
  Canvas: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useFrame: () => undefined,
}));
vi.mock("@react-three/drei", () => ({
  OrbitControls: () => null,
  Html: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

import MissionControl from "@/app/page";
import GhostLab from "@/app/ghost-lab/page";
import PatchForge from "@/app/patch-forge/page";
import VictoryReplay from "@/app/victory-replay/page";
import CausalConstellation from "@/app/causal-constellation/page";
import EvidenceVault from "@/app/evidence-vault/page";
import RealityRewind from "@/app/reality-rewind/page";
import HolographicReconstruction from "@/app/holographic-reconstruction/page";
import { ReportPage } from "@/app/reports/page";

const PAGES: Array<[string, React.ComponentType]> = [
  ["MissionControl", MissionControl],
  ["GhostLab", GhostLab],
  ["PatchForge", PatchForge],
  ["VictoryReplay", VictoryReplay],
  ["CausalConstellation", CausalConstellation],
  ["EvidenceVault", EvidenceVault],
  ["RealityRewind", RealityRewind],
  ["HolographicReconstruction", HolographicReconstruction],
  ["ReportPage", ReportPage],
];

async function resolveAuth() {
  await act(async () => {
    authMock.state.isLoading = false;
    authMock.state.isAuthenticated = true;
    authMock.listeners.forEach((l) => l());
  });
}

describe("auth gate does not break the rules of hooks", () => {
  beforeEach(() => {
    authMock.state.isAuthenticated = false;
    authMock.state.isLoading = true;
    authMock.listeners.clear();
  });

  it.each(PAGES)("%s survives the auth-loading -> authenticated transition", async (_name, Page) => {
    // React logs the "Rendered more hooks than during the previous render."
    // error and re-throws it during render, so a violation fails the test.
    const errors: unknown[] = [];
    const spy = vi.spyOn(console, "error").mockImplementation((...args: unknown[]) => {
      errors.push(args[0]);
    });

    try {
      render(<Page />);
      await resolveAuth();
    } finally {
      spy.mockRestore();
    }

    const hookErrors = errors.filter(
      (e) => typeof e === "string" && e.includes("Rendered more hooks")
    );
    expect(hookErrors, "page violates the rules of hooks").toHaveLength(0);
  });
});
