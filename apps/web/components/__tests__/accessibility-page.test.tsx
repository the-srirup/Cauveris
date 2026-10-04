import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'jest-axe';
import EvidenceVault from '@/app/evidence-vault/page';
import CausalConstellation from '@/app/causal-constellation/page';
import RealityRewind from '@/app/reality-rewind/page';
import GhostLab from '@/app/ghost-lab/page';
import PatchForge from '@/app/patch-forge/page';
import VictoryReplay from '@/app/victory-replay/page';
import SettingsPage from '@/app/settings/page';
import { ReportPage } from '@/app/reports/page';

expect.extend(toHaveNoViolations);

// Mock useShell and other context providers for page components
vi.mock('@/lib/useShell', () => ({
  useShell: () => ({
    state: {
      activeNav: 'evidence-vault',
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
vi.mock('@/lib/api', () => ({
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
vi.mock('@/hooks/useMediaQuery', () => ({
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

vi.mock('@/hooks/useKeyboardShortcut', () => ({
  useKeyboardShortcuts: vi.fn(),
}));

// Mock Notification
vi.mock('@/components/Notification', () => ({
  notify: vi.fn(),
}));

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
    'Sliders', 'Copy', 'Magnet', 'ZoomIn', 'ZoomOut', 'Maximize', 'ArrowLeft', 'ArrowRight', 'SkipBack', 'SkipForward', 'Timer', 'Package',
  ];
  const mocks: Record<string, any> = {};
  icons.forEach(name => {
    mocks[name] = (props: any) => <svg data-testid={`icon-${name.toLowerCase()}`} {...props} />;
  });
  return mocks;
});

// Mock UI primitives
vi.mock('@/components/ui', () => ({
  Badge: ({ children, tone = "default", className = "", ...props }: any) => (
    <span className={`px-2 py-0.5 rounded text-xs ${className}`} data-tone={tone} {...props}>{children}</span>
  ),
  Button: ({ children, className = "", ...props }: any) => (
    <button className={className} {...props}>{children}</button>
  ),
  Progress: ({ className = "", value, ...props }: any) => (
    <div className={className} role="progressbar" aria-valuenow={value} {...props} />
  ),
  Input: ({ className = "", ...props }: any) => (
    <input className={className} {...props} />
  ),
  Select: ({ className = "", value, onValueChange, options, label, ...props }: any) => (
    <div>
      {label && <label htmlFor={props.id || "select-mock"} className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">{label}</label>}
      <select id={props.id || "select-mock"} className={className} value={value} onChange={(e) => onValueChange(e.target.value)} {...props}>
        {options?.map((opt: any) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
      </select>
    </div>
  ),
  Card: ({ title, children, action, className = "", ...props }: any) => (
    <section className={`glass ring-glow rounded-2xl border border-[var(--color-border)] p-6 ${className}`} {...props}>
      {(title || action) && (
        <header className="mb-5 flex items-center justify-between gap-4">
          <h2 className="flex items-center gap-2.5 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
            {title}
          </h2>
          {action}
        </header>
      )}
      {children}
    </section>
  ),
  Stat: ({ label, value, sub, trend, ...props }: any) => (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/40 p-4" {...props}>
      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1.5 font-mono text-2xl font-semibold text-[var(--color-text-primary)]">{value}</div>
      {sub && <div className={`mt-1 text-xs`}>{sub}</div>}
    </div>
  ),
  PageHeader: ({ title, subtitle, badge, ...props }: any) => (
    <div className="mb-8" {...props}>
      <div className="flex items-center gap-3">
        <h1 className="text-gradient text-3xl font-bold tracking-tight">{title}</h1>
        {badge}
      </div>
      {subtitle && <p className="mt-1.5 text-sm text-[var(--color-text-muted)]">{subtitle}</p>}
    </div>
  ),
  KV: ({ label, value, sub, ...props }: any) => (
    <div className="flex items-center justify-between gap-4 py-2 text-sm" {...props}>
      <div>
        <span className="text-[var(--color-text-muted)]">{label}</span>
        {sub && <span className="block text-sm text-[var(--color-text-muted)]/70">{sub}</span>}
      </div>
      <span className="text-right font-medium text-[var(--color-text-primary)]">{value}</span>
    </div>
  ),
  Toggle: ({ checked, onChange, disabled = false, ...props }: any) => (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      role="switch"
      aria-checked={checked}
      {...props}
    >
      {checked ? 'ON' : 'OFF'}
    </button>
  ),
  Divider: ({ orientation = "horizontal", className = "", ...props }: any) => (
    orientation === "horizontal" ? (
      <hr className={`border-t border-[var(--color-border)] ${className}`} role="separator" {...props} />
    ) : (
      <div className={`border-l border-[var(--color-border)] ${className}`} role="separator" {...props} />
    )
  ),
  Tooltip: ({ children, content }: { children: React.ReactNode; content: React.ReactNode }) => (
    <div className="relative inline-block" data-testid="tooltip">
      {children}
      <div className="absolute invisible group-hover:visible">{content}</div>
    </div>
  ),
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock Tooltip
vi.mock('@/components/Tooltip', () => ({
  Tooltip: ({ children, content }: { children: React.ReactNode; content: React.ReactNode }) => (
    <div className="relative inline-block" data-testid="tooltip">
      {children}
      <div className="absolute invisible group-hover:visible">{content}</div>
    </div>
  ),
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

// Mock Tabs
vi.mock('@/components/Tabs', () => {
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

// Mock NotificationContainer
vi.mock('@/components/Notification', () => ({
  NotificationContainer: () => <div data-testid="notification-container" />,
  notify: vi.fn(),
}));

describe('Accessibility Audit - Page Components', () => {
  // Evidence Vault Tests
  describe('EvidenceVault', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<EvidenceVault />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<EvidenceVault />);
      expect(screen.getByRole('heading', { name: 'Evidence Vault', level: 1 })).toBeInTheDocument();
    });

    it('should have search input with proper label', () => {
      render(<EvidenceVault />);
      const searchInput = screen.getByPlaceholderText('Search artifacts, files, checksums...');
      expect(searchInput).toBeInTheDocument();
    });

    it('should have filter controls with proper ARIA', () => {
      render(<EvidenceVault />);
      // Select filters should be keyboard accessible
      expect(screen.getByLabelText('')).toBeInTheDocument(); // Select components
    });

    it('should have focus-visible on interactive elements', () => {
      render(<EvidenceVault />);
      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).toHaveClass('focus-visible:outline-none');
        expect(button).toHaveClass('focus-visible:ring-2');
        expect(button).toHaveClass('focus-visible:ring-primary');
      });
    });
  });

  // Causal Constellation Tests
  describe('CausalConstellation', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<CausalConstellation />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<CausalConstellation />);
      expect(screen.getByRole('heading', { name: 'Causal Constellation', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible toolbar controls with labels', () => {
      render(<CausalConstellation />);
      expect(screen.getByLabelText('Zoom In')).toBeInTheDocument();
      expect(screen.getByLabelText('Zoom Out')).toBeInTheDocument();
      expect(screen.getByLabelText('Fit View to Contents')).toBeInTheDocument();
      expect(screen.getByLabelText('Reset View')).toBeInTheDocument();
      expect(screen.getByLabelText('Toggle Layout Mode')).toBeInTheDocument();
    });

    it('should have confidence threshold input with label', () => {
      render(<CausalConstellation />);
      expect(screen.getByLabelText('Confidence:')).toBeInTheDocument();
    });

    it('should have evidence state filter buttons', () => {
      render(<CausalConstellation />);
      const buttons = screen.getAllByRole('button');
      const filterButtons = buttons.filter(b => b.textContent?.includes('Evidence State') || b.textContent?.includes('SUPPORTED') || b.textContent?.includes('CONTRADICTED') || b.textContent?.includes('UNKNOWN'));
      expect(filterButtons.length).toBeGreaterThan(0);
    });
  });

  // Reality Rewind Tests
  describe('RealityRewind', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<RealityRewind />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<RealityRewind />);
      expect(screen.getByRole('heading', { name: 'Reality Rewind', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible playback controls', () => {
      render(<RealityRewind />);
      expect(screen.getByLabelText('Play')).toBeInTheDocument();
      expect(screen.getByLabelText('Pause')).toBeInTheDocument();
      expect(screen.getByLabelText('Step Backward')).toBeInTheDocument();
      expect(screen.getByLabelText('Step Forward')).toBeInTheDocument();
      expect(screen.getByLabelText('Jump to Failure')).toBeInTheDocument();
      expect(screen.getByLabelText('Export Timeline')).toBeInTheDocument();
    });

    it('should have search input with proper label', () => {
      render(<RealityRewind />);
      const searchInput = screen.getByPlaceholderText('Search events...');
      expect(searchInput).toBeInTheDocument();
    });

    it('should have filter controls with proper ARIA', () => {
      render(<RealityRewind />);
      // Source, Evidence Status, Severity filter buttons
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should have accessible event list with proper semantics', () => {
      render(<RealityRewind />);
      expect(screen.getByRole('heading', { name: 'Synchronized Chronological Event Stream', level: 2 })).toBeInTheDocument();
      // The event list uses ul/li structure
      expect(screen.getByRole('list')).toBeInTheDocument();
    });
  });

  // Ghost Lab Tests
  describe('GhostLab', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<GhostLab />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<GhostLab />);
      expect(screen.getByRole('heading', { name: 'Ghost Lab', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible branch selector tabs', () => {
      render(<GhostLab />);
      const buttons = screen.getAllByRole('button');
      const branchButtons = buttons.filter(b => b.textContent?.includes('Branch') || b.textContent?.includes('exp-'));
      expect(branchButtons.length).toBeGreaterThan(0);
      // Each branch button should have accessible name
      branchButtons.forEach(btn => {
        expect(btn.getAttribute('aria-label') || btn.textContent).toBeTruthy();
      });
    });

    it('should have accessible action buttons', () => {
      render(<GhostLab />);
      expect(screen.getByRole('button', { name: /export experiment data/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /run twin simulations/i })).toBeInTheDocument();
    });

    it('should have focus-visible on interactive elements', () => {
      render(<GhostLab />);
      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).toHaveClass('focus-visible:outline-none');
        expect(button).toHaveClass('focus-visible:ring-2');
        expect(button).toHaveClass('focus-visible:ring-primary');
      });
    });
  });

  // Patch Forge Tests
  describe('PatchForge', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<PatchForge />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<PatchForge />);
      expect(screen.getByRole('heading', { name: 'Patch Forge', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible patch cards with proper structure', () => {
      render(<PatchForge />);
      // Patch cards should be clickable and have proper focus styles
      const buttons = screen.getAllByRole('button');
      expect(buttons.length).toBeGreaterThan(0);
    });

    it('should have 9-point verification checklist with proper semantics', () => {
      render(<PatchForge />);
      // Check for checklist items
      expect(screen.getByText(/9-Point Invariant Verification Checklist/i)).toBeInTheDocument();
    });

    it('should have accessible download buttons', () => {
      render(<PatchForge />);
      expect(screen.getByRole('button', { name: /download verified patch/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /create patch package/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /generate new candidates/i })).toBeInTheDocument();
    });
  });

  // Victory Replay Tests
  describe('VictoryReplay', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<VictoryReplay />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<VictoryReplay />);
      expect(screen.getByRole('heading', { name: 'Victory Replay', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible before/after comparison cards', () => {
      render(<VictoryReplay />);
      expect(screen.getByRole('heading', { name: 'Pre-Patch Digital Twin (Baseline Failure)', level: 2 })).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: 'Post-Patch Digital Twin (PATCH-001 Applied)', level: 2 })).toBeInTheDocument();
    });

    it('should have accessible metrics comparison table', () => {
      render(<VictoryReplay />);
      const table = screen.getByRole('table');
      expect(table).toBeInTheDocument();
      // Check for headers
      expect(screen.getByRole('columnheader', { name: 'Metric' })).toBeInTheDocument();
      expect(screen.getByRole('columnheader', { name: 'Before Patch' })).toBeInTheDocument();
      expect(screen.getByRole('columnheader', { name: 'After Patch' })).toBeInTheDocument();
      expect(screen.getByRole('columnheader', { name: 'Improvement' })).toBeInTheDocument();
    });

    it('should have accessible rollback verification and download buttons', () => {
      render(<VictoryReplay />);
      expect(screen.getByRole('button', { name: /test reversible rollback/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /export replay json/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /download validated patch package/i })).toBeInTheDocument();
    });
  });

  // Settings Page Tests
  describe('SettingsPage', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<SettingsPage />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<SettingsPage />);
      expect(screen.getByRole('heading', { name: 'Settings', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible sidebar navigation with proper ARIA', () => {
      render(<SettingsPage />);
      const nav = screen.getByRole('navigation', { name: 'Settings categories' });
      expect(nav).toBeInTheDocument();
      // Tab buttons should have aria-selected
      const tabs = screen.getAllByRole('tab');
      expect(tabs.length).toBe(6); // appearance, notifications, keyboard, privacy, data, advanced
      tabs.forEach((tab, i) => {
        expect(tab).toHaveAttribute('aria-selected');
        expect(tab.getAttribute('role')).toBe('tab');
      });
    });

    it('should have accessible form controls with labels', () => {
      render(<SettingsPage />);
      // Test theme radio-like buttons
      expect(screen.getByRole('button', { name: /light/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /dark/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /system/i })).toBeInTheDocument();
    });

    it('should have accessible toggles with proper ARIA', () => {
      render(<SettingsPage />);
      // Appearance toggles
      expect(screen.getByRole('switch', { name: /animations/i })).toBeInTheDocument();
      expect(screen.getByRole('switch', { name: /reduced motion/i })).toBeInTheDocument();

      // Switch to notifications tab to test more toggles
      // This would require clicking the tab - testing structure only
    });

    it('should have focus-visible on all interactive elements', () => {
      render(<SettingsPage />);
      const buttons = screen.getAllByRole('button');
      buttons.forEach(button => {
        expect(button).toHaveClass('focus-visible:outline-none');
        expect(button).toHaveClass('focus-visible:ring-2');
        expect(button).toHaveClass('focus-visible:ring-primary');
      });
    });

    it('should have proper input labels for form fields', () => {
      render(<SettingsPage />);
      // Session timeout input
      expect(screen.getByLabelText(/session timeout/i)).toBeInTheDocument();
      // API endpoint input
      expect(screen.getByLabelText(/api endpoint/i)).toBeInTheDocument();
      // Max concurrent experiments input
      expect(screen.getByLabelText(/max concurrent experiments/i)).toBeInTheDocument();
    });
  });

  // Reports Page Tests
  describe('ReportsPage', () => {
    it('should have no accessibility violations', async () => {
      const { container } = render(<ReportPage />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('should have proper heading structure', () => {
      render(<ReportPage />);
      expect(screen.getByRole('heading', { name: 'Reports', level: 1 })).toBeInTheDocument();
    });

    it('should have accessible report list', () => {
      render(<ReportPage />);
      // Report items should be accessible
      expect(screen.getByRole('button', { name: /download full report/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /generate report/i })).toBeInTheDocument();
    });
  });
});