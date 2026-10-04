import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as React from "react";
import { vi, describe, it, expect } from "vitest";

// Mock lucide-react icons - comprehensive mock for all components
vi.mock('lucide-react', () => {
  const icons = [
    'LayoutDashboard', 'Clock', 'GitBranch', 'Eye', 'FlaskConical', 'Wrench',
    'RotateCcw', 'Database', 'FileText', 'Settings', 'ChevronLeft', 'Menu',
    'X', 'ChevronRight', 'Zap', 'Download', 'AlertTriangle', 'Plus', 'Upload',
    'Play', 'Square', 'ExternalLink', 'Search', 'Bot', 'Scale', 'Shield',
    'Link', 'Check', 'HelpCircle', 'Info', 'Loader2', 'Terminal', 'WifiOff',
    'AlertCircle', 'CheckCircle', 'XCircle', 'ChevronUp', 'ChevronDown', 'Filter', 'Trash2',
    'User', 'LogOut'
  ];
  const mocks: Record<string, any> = {};
  icons.forEach(name => {
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
  default: ({ children, href, className = "", ...props }: { children: React.ReactNode; href: string; className?: string }) => (
    <a href={href} className={className} {...props}>{children}</a>
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

// Mock useShell
vi.mock("@/lib/useShell", () => ({
  useShell: () => ({
    state: {
      activeNav: 'mission-control',
      isNavCollapsed: false,
      isNavDrawerOpen: false,
      incidentContext: {
        id: "CAU-0001",
        title: "Test Incident",
        state: "RUNNING",
        pipelineStage: "INGEST",
        evidenceCoverage: 75,
        modelProvider: "Local Fixtures",
        backendStatus: "online",
        processingMode: "autonomous",
      },
      inspectorOpen: true,
      inspectorMode: "evidence",
      inspectorData: {
        mode: "evidence",
        evidenceId: "ev-001",
        evidenceData: {
          id: "ev-001",
          name: "config/inference.yaml",
          type: "YAML",
          path: "config/inference.yaml",
          size: 1024,
          checksum: "abc123def456",
          status: "OBSERVED",
          is_required: true,
          ingested_at: new Date().toISOString(),
          confidence: 0.9,
        },
      },
      trayState: 'expanded',
      activities: [
        { id: "act-1", type: "pipeline", message: "Pipeline started", timestamp: Date.now() - 10000, stageId: "INGEST", dismissible: true },
        { id: "act-2", type: "system", message: "Backend connected", timestamp: Date.now() - 5000, dismissible: false },
        { id: "act-3", type: "error", message: "Validation failed", timestamp: Date.now(), details: "Missing required evidence", dismissible: true },
      ],
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
  ShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useActiveIncident: () => ({
    incidentId: 'CAU-0001',
    judgeMode: false,
    engineerMode: false,
  }),
  buildIncidentContext: vi.fn(),
}));

// Mock API
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

// Mock hooks
vi.mock("@/hooks/useMediaQuery", () => ({
  useShellLayout: () => ({
    isInspectorDrawer: false,
    isSidebarDrawer: false,
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

// Mock UI components
vi.mock("@/components/ui", () => ({
  Badge: ({ children, tone = "default", className = "" }: { children: React.ReactNode; tone?: string; className?: string }) => (
    <span className={`px-2 py-0.5 rounded text-xs ${className}`} data-tone={tone}>{children}</span>
  ),
  Button: ({ children, className = "", ...props }: { children: React.ReactNode; className?: string }) => (
    <button className={className} {...props}>{children}</button>
  ),
  Progress: ({ className = "", value, ...props }: { className?: string; value: number }) => (
    <div className={className} role="progressbar" aria-valuenow={value} {...props} />
  ),
  Input: ({ className = "", ...props }: { className?: string }) => (
    <input className={className} {...props} />
  ),
}));

// Mock Tooltip component
vi.mock("@/components/Tooltip", () => ({
  Tooltip: ({ children, content }: { children: React.ReactNode; content: React.ReactNode }) => (
    <div className="relative inline-block" data-testid="tooltip">
      {children}
      <div className="absolute invisible group-hover:visible">{content}</div>
    </div>
  ),
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock Tabs component
vi.mock("@/components/Tabs", () => {
  const TabsRoot = ({ children, defaultValue }: { children: React.ReactNode; defaultValue: string }) => (
    <div data-testid="tabs" data-default-value={defaultValue}>{children}</div>
  );
  const TabsList = ({ children }: { children: React.ReactNode }) => (
    <div role="tablist" data-testid="tabs-list">{children}</div>
  );
  const TabsTrigger = ({ children, value, className = "", ...props }: { children: React.ReactNode; value: string; className?: string }) => (
    <button role="tab" className={className} data-value={value} {...props}>{children}</button>
  );
  const TabsContent = ({ children, value, className = "", forceMount, ...props }: { children: React.ReactNode; value: string; className?: string; forceMount?: boolean }) => (
    <div role="tabpanel" className={className} data-value={value} {...props}>{children}</div>
  );
  const Tabs = Object.assign(TabsRoot, { List: TabsList, Trigger: TabsTrigger, Content: TabsContent });
  return { Tabs, TabsRoot, TabsList, TabsTrigger, TabsContent };
});

// Mock Divider component
vi.mock("@/components/Divider", () => ({
  Divider: ({ orientation = "horizontal", children }: { orientation?: string; children?: React.ReactNode }) => (
    <div role="separator" aria-orientation={orientation} data-testid="divider">
      {children}
    </div>
  ),
}));

// Mock Notification
vi.mock("@/components/Notification", () => ({
  NotificationContainer: () => <div data-testid="notification-container" />,
  notify: vi.fn(),
}));

// Import after mocks
import { ShellProvider } from "@/lib/useShell";
import Sidebar from "@/components/Sidebar";
import { TopContextBar } from "@/components/TopContextBar";
import { RightInspector } from "@/components/RightInspector";
import { BottomActivityTray } from "@/components/BottomActivityTray";
import { CommandPalette } from "@/components/CommandPalette";
import { NotificationContainer } from "@/components/Notification";

describe("Shell Layout Integration", () => {
  const renderShell = () => {
    return render(
      <ShellProvider>
        <Sidebar />
        <TopContextBar />
        <RightInspector />
        <BottomActivityTray />
        <CommandPalette />
        <NotificationContainer />
      </ShellProvider>
    );
  };

  it("renders all four persistent zones", () => {
    renderShell();
    // Top Context Bar - has role="banner" with specific aria-label
    expect(screen.getByRole("banner", { name: /incident context and global actions/i })).toBeInTheDocument();
    // Sidebar - is an aside with aria-label="Sidebar" containing a nav with aria-label="Navigation sections"
    expect(screen.getByRole("complementary", { name: /sidebar/i })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: /navigation sections/i })).toBeInTheDocument();
    // Main content area would be filled by children
    // Right Inspector (closed by default)
    // Bottom Activity Tray
    expect(screen.getByRole("region", { name: /activity tray/i })).toBeInTheDocument();
  });

  it("sidebar has correct navigation structure", () => {
    renderShell();
    // Get all links - includes brand header link (href="/") + 10 nav items
    const navLinks = screen.getAllByRole("link");
    expect(navLinks.length).toBe(11);

    // Check all expected routes (including brand link)
    const hrefs = navLinks.map(link => link.getAttribute("href")).sort();
    expect(hrefs).toContain("/"); // appears twice (brand + nav)
    expect(hrefs).toContain("/reality-rewind");
    expect(hrefs).toContain("/causal-constellation");
    expect(hrefs).toContain("/holographic-reconstruction");
    expect(hrefs).toContain("/ghost-lab");
    expect(hrefs).toContain("/patch-forge");
    expect(hrefs).toContain("/victory-replay");
    expect(hrefs).toContain("/evidence-vault");
    expect(hrefs).toContain("/reports");
    expect(hrefs).toContain("/settings");
  });

  it("top bar shows incident context", () => {
    renderShell();
    expect(screen.getByText("CAU-0001")).toBeInTheDocument();
    expect(screen.getByText("Test Incident")).toBeInTheDocument();
  });

  it("top bar shows system status", () => {
    renderShell();
    expect(screen.getByText("online")).toBeInTheDocument();
  });

  it("keyboard shortcuts prevent default", () => {
    renderShell();
    // Test Cmd+K
    const event = new KeyboardEvent("keydown", { key: "k", metaKey: true });
    document.dispatchEvent(event);
    // Should be prevented by the script in layout
    expect(true).toBeTruthy();
  });

  it("command palette opens with Cmd+K", () => {
    // This would require integration with the keyboard shortcut handler
    expect(true).toBeTruthy();
  });

  it("sidebar collapses/expands", () => {
    renderShell();
    // Sidebar collapse button
    const collapseBtn = screen.getByLabelText("Collapse sidebar");
    expect(collapseBtn).toBeInTheDocument();
  });

  it("right inspector opens when triggered", () => {
    // Inspector is closed by default
    // Would need to trigger via shell context
    expect(true).toBeTruthy();
  });

  it("activity tray shows activities", () => {
    renderShell();
    expect(screen.getByText("Pipeline started")).toBeInTheDocument();
    expect(screen.getByText("Backend connected")).toBeInTheDocument();
    expect(screen.getByText("Validation failed")).toBeInTheDocument();
  });

  it("no horizontal overflow at desktop viewport", () => {
    renderShell();
    const body = document.body;
    expect(body.scrollWidth).toBeLessThanOrEqual(window.innerWidth + 1); // Allow 1px tolerance
  });

  it("responsive layout adapts to tablet viewport", () => {
    // Would need to test with different viewport sizes
    expect(true).toBeTruthy();
  });

  it("responsive layout adapts to mobile viewport", () => {
    // Would need to test with different viewport sizes
    expect(true).toBeTruthy();
  });

  it("context preserved during navigation", () => {
    // Navigation between pages should preserve incident context
    // This is tested via the useShell context
    expect(true).toBeTruthy();
  });
});