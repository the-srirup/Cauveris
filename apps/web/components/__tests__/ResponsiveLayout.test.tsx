import { render, screen, fireEvent, act } from "@testing-library/react";
import * as React from "react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Use real useShell provider and hook implementation for responsive layout testing
vi.unmock("@/lib/useShell");

// Mock lucide-react icons
vi.mock("lucide-react", () => {
  const icons = [
    "LayoutDashboard", "Clock", "GitBranch", "Eye", "FlaskConical", "Wrench",
    "RotateCcw", "Database", "FileText", "Settings", "ChevronLeft", "Menu",
    "X", "ChevronRight", "Zap", "Download", "AlertTriangle", "Plus", "Upload",
    "Play", "Square", "ExternalLink", "Search", "Bot", "Scale", "Shield",
    "Link", "Check", "HelpCircle", "Info", "Loader2", "Terminal", "WifiOff",
    "AlertCircle", "CheckCircle", "XCircle", "ChevronUp", "ChevronDown", "Filter", "Trash2",
    "User", "LogOut"
  ];
  const mocks: Record<string, any> = {};
  icons.forEach((name) => {
    mocks[name] = (props: any) => <svg data-testid={`icon-${name.toLowerCase()}`} {...props} />;
  });
  return mocks;
});

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: vi.fn(() => "/"),
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

// Mock next/link
vi.mock("next/link", () => ({
  default: React.forwardRef<HTMLAnchorElement, { children: React.ReactNode; href: string; className?: string }>(
    ({ children, href, className = "", ...props }, ref) => (
      <a ref={ref} href={href} className={className} {...props}>{children}</a>
    )
  ),
}));

// Mock useIncident
vi.mock("@/lib/useIncident", () => ({
  useActiveIncident: () => ({
    incident: { id: "CAU-0001", title: "Test Incident" },
    incidentId: "CAU-0001",
    judgeMode: false,
    engineerMode: false,
    setIncidentId: vi.fn(),
    loadIncident: vi.fn(),
  }),
}));

// Mock api
vi.mock("@/lib/api", () => ({
  api: {
    create: vi.fn().mockResolvedValue({ incident_id: "CAU-0002" }),
    reconstruct: vi.fn(),
    cancel: vi.fn(),
    exportReport: vi.fn().mockResolvedValue({}),
    resetDemo: vi.fn(),
    health: vi.fn().mockResolvedValue({ status: "healthy" }),
    modelHealth: vi.fn().mockResolvedValue({ status: "healthy", provider: "Local Fixtures" }),
  },
}));

// Mock useMediaQuery with controllable breakpoint
let mockBreakpoint = "desktop";
let mockIsSidebarDrawer = false;
let mockIsInspectorDrawer = false;

vi.mock("@/hooks/useMediaQuery", () => ({
  useShellLayout: () => ({
    breakpoint: mockBreakpoint,
    isInspectorDrawer: mockIsInspectorDrawer,
    isSidebarDrawer: mockIsSidebarDrawer,
    isMobile: mockBreakpoint === "mobile",
    isTablet: mockBreakpoint === "tablet",
    isLaptop: mockBreakpoint === "laptop",
    isDesktop: mockBreakpoint === "desktop",
  }),
  useMediaQuery: () => false,
  useBreakpoint: () => mockBreakpoint,
  useViewport: () => ({ width: 1440, height: 900 }),
}));

// Mock auth store
vi.mock("@/lib/auth", () => ({
  useAuthStore: () => ({
    user: { id: "test-user", name: "Operator" },
    isAuthenticated: true,
  }),
}));

import { ShellProvider, useShell } from "@/lib/useShell";
import ShellLayout from "@/components/ShellLayout";

function TestConsumer({ onState }: { onState: (state: any) => void }) {
  const { state } = useShell();
  React.useEffect(() => {
    onState(state);
  }, [state, onState]);
  return null;
}

describe("Responsive Layout & Dynamic Sidebar Expansion", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockBreakpoint = "desktop";
    mockIsSidebarDrawer = false;
    mockIsInspectorDrawer = false;
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("1. renders the sidebar in expanded state initially", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    expect(sidebar).toHaveAttribute("data-collapsed", "false");
    expect(sidebar).toHaveClass("w-60");

    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid).toHaveAttribute("data-sidebar-collapsed", "false");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");
  });

  it("2. main content uses the reduced available width when expanded", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    const sidebarCol = document.getElementById("shell-sidebar-col");
    expect(sidebarCol?.style.width).toBe("240px");

    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid?.style.gridTemplateColumns).toContain("var(--shell-sidebar-current-width)");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");

    const main = screen.getByRole("main");
    expect(main).toHaveClass("lg:col-start-2");
  });

  it("3. sidebar can be collapsed via the toggle button", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    const toggleBtn = screen.getByLabelText("Collapse sidebar");
    fireEvent.click(toggleBtn);

    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    expect(sidebar).toHaveAttribute("data-collapsed", "true");
    expect(sidebar).toHaveClass("w-16");
  });

  it("4. main content expands leftward after collapse", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    // Initial state
    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");

    // Collapse
    const toggleBtn = screen.getByLabelText("Collapse sidebar");
    fireEvent.click(toggleBtn);

    // Sidebar column drops from 240px to 64px, freeing 176px for main content
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("64px");
    const sidebarCol = document.getElementById("shell-sidebar-col");
    expect(sidebarCol?.style.width).toBe("64px");
  });

  it("5. no unused sidebar-sized gap remains after collapse", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    const toggleBtn = screen.getByLabelText("Collapse sidebar");
    fireEvent.click(toggleBtn);

    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    const sidebarCol = document.getElementById("shell-sidebar-col");

    // Sidebar element width is 64px (w-16 = 4rem = 64px)
    expect(sidebar).toHaveClass("w-16");
    // Column 1 width is exactly 64px
    expect(sidebarCol?.style.width).toBe("64px");
    // Main starts at col 2 right at 64px, without 240px constraint
    const main = screen.getByRole("main");
    expect(main).toHaveClass("lg:col-start-2");
    expect(main).not.toHaveClass("ml-[240px]");
    expect(main).not.toHaveClass("pl-[240px]");
  });

  it("6. reopening the sidebar restores the expanded layout", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    // Collapse
    const collapseBtn = screen.getByLabelText("Collapse sidebar");
    fireEvent.click(collapseBtn);

    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("64px");

    // Expand
    const expandBtn = screen.getByLabelText("Expand sidebar");
    fireEvent.click(expandBtn);

    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");
    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    expect(sidebar).toHaveClass("w-60");
    expect(sidebar).toHaveAttribute("data-collapsed", "false");
  });

  it("7. rapid repeated toggling does not break the layout", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="page-content">Main Content Area</div>
        </ShellLayout>
      </ShellProvider>
    );

    const grid = document.getElementById("cauveris-shell-grid");

    // Toggle 10 times rapidly
    for (let i = 0; i < 10; i++) {
      const btn = screen.getByRole("button", { name: /(expand|collapse) sidebar/i });
      fireEvent.click(btn);
    }

    // After an even number of toggles (10), should be back to expanded (240px)
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");
    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    expect(sidebar).toHaveAttribute("data-collapsed", "false");
  });

  it("8. route navigation does not reset the state unexpectedly", () => {
    let capturedState: any;
    const { rerender } = render(
      <ShellProvider>
        <TestConsumer onState={(s) => (capturedState = s)} />
        <ShellLayout>
          <div data-testid="page-content">Mission Control</div>
        </ShellLayout>
      </ShellProvider>
    );

    // Collapse sidebar
    fireEvent.click(screen.getByLabelText("Collapse sidebar"));
    expect(capturedState.isNavCollapsed).toBe(true);

    // Simulate route navigation by rendering new children within same provider
    rerender(
      <ShellProvider>
        <TestConsumer onState={(s) => (capturedState = s)} />
        <ShellLayout>
          <div data-testid="page-content">Causal Constellation</div>
        </ShellLayout>
      </ShellProvider>
    );

    expect(capturedState.isNavCollapsed).toBe(true);
    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("64px");
  });

  it("9. the right inspector does not overlap the central content", () => {
    function InspectorTrigger() {
      const { openInspector, closeInspector } = useShell();
      return (
        <div>
          <button onClick={() => openInspector("evidence", { mode: "evidence" })}>
            Open Inspector
          </button>
          <button onClick={() => closeInspector()}>Close Inspector</button>
        </div>
      );
    }

    render(
      <ShellProvider>
        <ShellLayout>
          <InspectorTrigger />
        </ShellLayout>
      </ShellProvider>
    );

    const grid = document.getElementById("cauveris-shell-grid");
    const inspectorCol = document.getElementById("shell-inspector-col");

    // Initially closed: 0px column
    expect(grid?.style.getPropertyValue("--shell-inspector-current-width")).toBe("0px");
    expect(inspectorCol?.style.width).toBe("0px");

    // Open inspector
    fireEvent.click(screen.getByText("Open Inspector"));

    // Inspector allocated 360px column on desktop, preventing overlap with main content
    expect(grid?.style.getPropertyValue("--shell-inspector-current-width")).toBe("360px");
    expect(inspectorCol?.style.width).toBe("360px");

    // Close inspector
    fireEvent.click(screen.getByText("Close Inspector"));
    expect(grid?.style.getPropertyValue("--shell-inspector-current-width")).toBe("0px");
    expect(inspectorCol?.style.width).toBe("0px");
  });

  it("10. graphs and charts receive resize event after transition completes", () => {
    const resizeListener = vi.fn();
    const layoutResizeListener = vi.fn();
    window.addEventListener("resize", resizeListener);
    window.addEventListener("cauveris:layout-resize", layoutResizeListener);

    render(
      <ShellProvider>
        <ShellLayout>
          <div data-testid="graph-container">Causal Graph</div>
        </ShellLayout>
      </ShellProvider>
    );

    // Collapse sidebar
    fireEvent.click(screen.getByLabelText("Collapse sidebar"));

    // Before transition completes (e.g. 100ms)
    act(() => {
      vi.advanceTimersByTime(100);
    });
    expect(resizeListener).not.toHaveBeenCalled();

    // After transition completes (200ms)
    act(() => {
      vi.advanceTimersByTime(100);
    });

    expect(resizeListener).toHaveBeenCalled();
    expect(layoutResizeListener).toHaveBeenCalled();

    window.removeEventListener("resize", resizeListener);
    window.removeEventListener("cauveris:layout-resize", layoutResizeListener);
  });

  it("11. keyboard users can operate the toggle via '[' shortcut and focus button", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <input data-testid="search-input" />
        </ShellLayout>
      </ShellProvider>
    );

    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");

    // Press '[' shortcut outside of input
    fireEvent.keyDown(window, { key: "[" });
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("64px");

    // Press '[' shortcut again to expand
    fireEvent.keyDown(window, { key: "[" });
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");

    // Typing '[' inside input does NOT toggle sidebar
    const input = screen.getByTestId("search-input");
    input.focus();
    fireEvent.keyDown(input, { key: "[" });
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("240px");

    // Toggle button has accessible focus styling
    const toggleBtn = screen.getByLabelText("Collapse sidebar");
    expect(toggleBtn).toHaveClass("focus-visible:ring-2");
  });

  it("12. reduced-motion settings are respected", () => {
    render(
      <ShellProvider>
        <ShellLayout>
          <div>Main Content</div>
        </ShellLayout>
      </ShellProvider>
    );

    const grid = document.getElementById("cauveris-shell-grid");
    expect(grid).toHaveClass("motion-reduce:transition-none");

    const sidebar = screen.getByRole("complementary", { name: /sidebar/i });
    expect(sidebar).toHaveClass("motion-reduce:transition-none");

    const main = screen.getByRole("main");
    expect(main).toHaveClass("motion-reduce:transition-none");
  });

  it("13. mobile and tablet drawer modes preserve 0px desktop grid allocation", () => {
    mockIsSidebarDrawer = true;
    mockBreakpoint = "tablet";

    render(
      <ShellProvider>
        <ShellLayout>
          <div>Tablet Content</div>
        </ShellLayout>
      </ShellProvider>
    );

    const grid = document.getElementById("cauveris-shell-grid");
    // When drawer mode is active, sidebar does not consume desktop grid columns
    expect(grid?.style.getPropertyValue("--shell-sidebar-current-width")).toBe("0px");
    const sidebarCol = document.getElementById("shell-sidebar-col");
    expect(sidebarCol?.style.width).toBe("0px");
  });

  it("14. no browser console errors are introduced during layout changes", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});

    render(
      <ShellProvider>
        <ShellLayout>
          <div>Clean Content</div>
        </ShellLayout>
      </ShellProvider>
    );

    fireEvent.click(screen.getByLabelText("Collapse sidebar"));
    act(() => {
      vi.advanceTimersByTime(250);
    });

    fireEvent.click(screen.getByLabelText("Expand sidebar"));
    act(() => {
      vi.advanceTimersByTime(250);
    });

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
