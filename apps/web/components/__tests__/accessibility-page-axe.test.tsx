import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import { ShellProvider } from '@/lib/useShell';

expect.extend(toHaveNoViolations);

// Mock lucide-react
vi.mock('lucide-react', () => {
  const icons = [
    'LayoutDashboard', 'Clock', 'GitBranch', 'Eye', 'EyeOff', 'FlaskConical', 'Wrench',
    'RotateCcw', 'Database', 'FileText', 'Settings', 'ChevronLeft', 'Menu',
    'X', 'ChevronRight', 'Zap', 'Download', 'AlertTriangle', 'Plus', 'Upload',
    'Play', 'Square', 'ExternalLink', 'Search', 'Bot', 'Scale', 'Shield',
    'Link', 'Check', 'HelpCircle', 'Info', 'Loader2', 'Terminal', 'WifiOff',
    'AlertCircle', 'CheckCircle', 'CheckCircle2', 'XCircle', 'ChevronUp', 'ChevronDown', 'Filter', 'Trash2',
    'Palette', 'Bell', 'Keyboard', 'Command', 'Globe', 'Moon', 'Sun', 'Monitor', 'Key', 'Server',
    'Sliders', 'Copy',
    'Magnet', 'ZoomIn', 'ZoomOut', 'Maximize', 'ArrowLeft', 'ArrowRight', 'SkipBack', 'SkipForward', 'Timer', 'Package', 'Wrench',
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
    replace: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
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
  buildIncidentContext: vi.fn(),
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
        isDemonstration: false,
      },
      inspectorOpen: false,
      inspectorMode: null,
      inspectorData: { mode: null },
      trayState: 'compact',
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
    get: vi.fn().mockResolvedValue({
      id: "CAU-0001",
      title: "Test Incident",
      system_name: "warehouse-amr-01",
      evidence_count: 10,
      required_evidence_count: 14,
      missing_required_evidence: [],
      evidence_items: [
        { file_path: "manifest.yaml", file_type: "YAML", size_bytes: 1024, checksum_sha256: "abc123", status: "OBSERVED", is_required: true },
        { file_path: "config/inference.yaml", file_type: "YAML", size_bytes: 512, checksum_sha256: "def456", status: "OBSERVED", is_required: true },
      ],
    }),
    getReport: vi.fn().mockResolvedValue({
      title: "Test Report",
      description: "Test Description",
      status: "COMPLETED",
      hypotheses: [
        { hypothesis_id: "h1", title: "Hypothesis 1", status: "CONFIRMED", causal_claim: "Test claim", confidence: 0.9 },
      ],
      experiments: [
        { experiment_id: "exp-h1", name: "Batching Window Experiment", status: "SUCCESS", reproduction_rate: 0.0, intervention: "batching_window_ms: 100" },
      ],
      patch_candidates: [
        { candidate_id: "patch-1", title: "Patch 1", verified: true, score: 0.97, rationale: "Test rationale" },
      ],
    }),
    getTimeline: vi.fn().mockResolvedValue({
      timeline_events: [
        { event_id: "evt-1", message: "Deployment started", source_type: "deployment", relative_timestamp_s: 0, status: "SUCCESS", source: "kubernetes" },
        { event_id: "evt-2", message: "Inference latency spike", source_type: "metric", relative_timestamp_s: 1.5, status: "WARNING", source: "prometheus" },
      ],
      clock_alignment: {},
    }),
    getTemporalAnalysis: vi.fn().mockResolvedValue({ confidence_score: 0.95 }),
    getTemporalVisualization: vi.fn().mockResolvedValue({
      bulk_nodes: [
        { id: "node-1", name: "Node 1", type: "service", health: 0.8, confidence: 0.9, metrics: { evidence_coverage: 0.8 }, position: [100, 100], size: 10, color: "#888" },
        { id: "node-2", name: "Node 2", type: "service", health: 0.6, confidence: 0.7, metrics: { evidence_coverage: 0.6 }, position: [200, 200], size: 10, color: "#888" },
      ],
      bulk_edges: [
        { source: "node-1", target: "node-2", type: "causes", thickness: 1, latency_ms: 10, color: "#10b981", source_health: 0.8, target_health: 0.6 },
      ],
    }),
    getExperiments: vi.fn().mockResolvedValue({
      experiments: [
        { experiment_id: "exp-h1", name: "Batching Window Test", status: "SUCCESS", reproduction_rate: 0.0, intervention: "config/inference.yaml: batching_window_ms = 100" },
      ],
    }),
    getPatches: vi.fn().mockResolvedValue({
      patch_candidates: [
        { candidate_id: "patch-1", title: "Patch 1", verified: true, score: 0.97, lines_changed: 1, affected_files: ["config/inference.yaml"], unified_diff: "diff...", rationale: "Test" },
      ],
      verification_reports: [],
    }),
    exportReport: vi.fn().mockResolvedValue({}),
    downloadPatchPackage: vi.fn().mockResolvedValue(new Blob()),
    exportPatch: vi.fn().mockResolvedValue("patch content"),
    applyPatch: vi.fn().mockResolvedValue({ success: true }),
    list: vi.fn().mockResolvedValue({ incidents: [] }),
    simulateCustom: vi.fn().mockResolvedValue({}),
  },
}));

// Mock hooks
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

// Mock Notification
vi.mock("@/components/Notification", () => ({
  NotificationContainer: () => <div data-testid="notification-container" />,
  notify: vi.fn(),
}));

// Import pages after mocks - use dynamic import
const EvidenceVault = (await import('@/app/evidence-vault/page')).default;
const CausalConstellation = (await import('@/app/causal-constellation/page')).default;
const RealityRewind = (await import('@/app/reality-rewind/page')).default;
const GhostLab = (await import('@/app/ghost-lab/page')).default;
const PatchForge = (await import('@/app/patch-forge/page')).default;
const VictoryReplay = (await import('@/app/victory-replay/page')).default;
const SettingsPage = (await import('@/app/settings/page')).default;
const ReportsPage = (await import('@/app/reports/page')).ReportsPage;

describe('Accessibility Audit - Page Components (axe-core)', () => {
  const renderPage = (page: React.ReactElement) => {
    return render(
      <ShellProvider>
        {page}
      </ShellProvider>
    );
  };

  // Evidence Vault Tests
  describe('EvidenceVault', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<EvidenceVault />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Causal Constellation Tests
  describe('CausalConstellation', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<CausalConstellation />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Reality Rewind Tests
  describe('RealityRewind', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<RealityRewind />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Ghost Lab Tests
  describe('GhostLab', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<GhostLab />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Patch Forge Tests
  describe('PatchForge', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<PatchForge />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Victory Replay Tests
  describe('VictoryReplay', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<VictoryReplay />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Settings Page Tests
  describe('SettingsPage', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<SettingsPage />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // Reports Page Tests
  describe('ReportsPage', () => {
    it('should have no accessibility violations', async () => {
      const { container } = renderPage(<ReportsPage />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});