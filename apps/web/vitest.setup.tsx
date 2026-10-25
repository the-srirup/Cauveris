import '@testing-library/jest-dom';
import { vi } from 'vitest';
import React from 'react';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  usePathname: () => '/',
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(),
}));

// Mock lucide-react - dynamic proxy + explicit properties for named imports
vi.mock('lucide-react', () => {
  const createMockIcon = (name: string) => {
    const MockIcon = (props: any) => <svg data-testid={`icon-${name}`} {...props} />;
    MockIcon.displayName = name;
    return MockIcon;
  };

  const icons = [
    'Zap', 'Database', 'GitBranch', 'FlaskConical', 'Wrench', 'Eye', 'EyeOff', 'FileText',
    'RotateCcw', 'Download', 'AlertTriangle', 'Plus', 'Upload', 'Play', 'Square',
    'ExternalLink', 'Clock', 'ChevronRight', 'ChevronLeft', 'Menu', 'X',
    'LayoutDashboard', 'Search', 'Bot', 'Scale', 'Shield', 'Link', 'Check',
    'HelpCircle', 'Info', 'Loader2', 'Terminal', 'WifiOff', 'AlertCircle',
    'CheckCircle', 'CheckCircle2', 'XCircle', 'ChevronUp', 'ChevronDown', 'Filter', 'Trash2',
    'Settings', 'Palette', 'Bell', 'Moon', 'Sun', 'Monitor', 'Globe', 'User',
    'Command', 'Sliders', 'Server', 'Key', 'ShieldAlert', 'ShieldCheck', 'LogOut',
    'Copy', 'CheckCheck', 'Maximize2', 'Minimize2', 'RefreshCw', 'ArrowLeft',
    'ArrowRight', 'Share2', 'History', 'Workflow', 'Code', 'Layers', 'GitPullRequest',
    'Cpu', 'Activity', 'BarChart3', 'PlayCircle', 'StopCircle', 'Lock', 'Unlock',
    'Magnet', 'ZoomIn', 'ZoomOut', 'Maximize', 'SkipBack', 'SkipForward', 'Timer',
    'Package', 'CheckSquare', 'SquareSlash', 'FileCode', 'Sparkles'
  ];

  const mockModule: Record<string, any> = {
    __esModule: true,
  };
  for (const name of icons) {
    mockModule[name] = createMockIcon(name);
  }
  mockModule.default = mockModule;

  // The icon set above is a hand-maintained list, so importing an icon that is
  // not on it (e.g. `Box`) throws "No 'Box' export is defined on the
  // 'lucide-react' mock" and takes the whole test file down with it. Proxy the
  // module so any icon name resolves to a stub, and cache the stubs so the
  // identity of a given icon is stable across renders.
  return new Proxy(mockModule, {
    get(target, prop: string | symbol) {
      if (typeof prop !== 'string') {
        return Reflect.get(target, prop);
      }
      // Never look like a thenable: Vitest awaits the mocked module.
      if (prop === 'then') return undefined;
      if (prop in target) {
        return Reflect.get(target, prop);
      }
      const icon = createMockIcon(prop);
      target[prop] = icon;
      return icon;
    },
    has(target, prop: string | symbol) {
      return typeof prop === 'string' ? true : Reflect.has(target, prop);
    },
  });
});

// Mock Shell context
const mockShellState = {
  activeNav: 'mission-control',
  isNavCollapsed: false,
  isNavDrawerOpen: false,
  incidentContext: null,
  inspectorOpen: false,
  inspectorMode: null,
  inspectorData: { mode: null },
  trayState: 'compact',
  activities: [],
  commandPaletteOpen: true,
};

const ShellContextValue = {
  state: mockShellState,
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
};

const ShellProvider = ({ children }: { children: React.ReactNode }) => (
  <ShellContext.Provider value={ShellContextValue}>{children}</ShellContext.Provider>
);

const ShellContext = React.createContext(ShellContextValue);

vi.mock('@/lib/useShell', () => ({
  useShell: () => ShellContextValue,
  useActiveIncident: () => ({
    incidentId: 'CAU-0001',
    judgeMode: false,
    engineerMode: false,
  }),
  buildIncidentContext: vi.fn(),
  ShellProvider,
  ShellContext,
}));

// Mock API
vi.mock('@/lib/api', async () => {
  const { victoryReplayFixture, applyPatchSuccessFixture } = await import(
    './components/__tests__/fixtures/victory-replay'
  );
  return {
    api: {
      get: vi.fn(),
      create: vi.fn(),
      reconstruct: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
      validate: vi.fn(),
      uploadFile: vi.fn(),
      getEvents: vi.fn(),
      getReport: vi.fn(),
      getTimeline: vi.fn(),
      getTemporalAnalysis: vi.fn(),
      health: vi.fn(),
      modelHealth: vi.fn(),
      list: vi.fn(),
      simulateCustom: vi.fn(),
      exportReport: vi.fn().mockResolvedValue({}),
      listReports: vi.fn().mockResolvedValue({ reports: [] }),
      deleteReport: vi.fn().mockResolvedValue({ message: "deleted" }),
      resetDemo: vi.fn(),
      downloadPatchPackage: vi.fn(),
      exportPatch: vi.fn(),
      applyPatch: vi.fn().mockResolvedValue(applyPatchSuccessFixture),
      getVictoryReplay: vi.fn().mockResolvedValue(victoryReplayFixture),
    },
  };
});

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

// Mock notification
vi.mock('@/components/Notification', () => ({
  notify: vi.fn(),
  NotificationContainer: () => <div data-testid="notification-container" />,
}));

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock @react-three/fiber and @react-three/drei for Node.js test environment
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children, ...props }: any) => <div data-testid="three-canvas" {...props}>{children}</div>,
  useFrame: vi.fn(),
  useThree: () => ({
    camera: { position: { x: 0, y: 0, z: 5 } },
    scene: {},
    gl: { domElement: { width: 800, height: 600 } },
    size: { width: 800, height: 600 },
    viewport: { width: 800, height: 600 },
    raycaster: {},
    mouse: { x: 0, y: 0 },
    clock: { getDelta: () => 0.016, getElapsedTime: () => 0 },
    performance: { now: () => Date.now() },
  }),
  extend: vi.fn(),
  createPortal: ({ children }: any) => children,
  events: { connect: vi.fn(), disconnect: vi.fn() },
}));

vi.mock('@react-three/drei', () => ({
  OrbitControls: ({ children, ...props }: any) => <div data-testid="orbit-controls" {...props}>{children}</div>,
  Html: ({ children, ...props }: any) => <div data-testid="drei-html" {...props}>{children}</div>,
  Text: ({ children, ...props }: any) => <div data-testid="drei-text" {...props}>{children}</div>,
  ContactShadows: ({ ...props }: any) => <div data-testid="contact-shadows" {...props} />,
  Stage: ({ children, ...props }: any) => <div data-testid="drei-stage" {...props}>{children}</div>,
  Environment: ({ children, ...props }: any) => <div data-testid="drei-environment" {...props}>{children}</div>,
  PerspectiveCamera: ({ children, ...props }: any) => <div data-testid="perspective-camera" {...props}>{children}</div>,
  useGLTF: vi.fn(() => ({ scene: {}, nodes: {}, materials: {} })),
  useTexture: vi.fn(() => ({})),
  MeshDistort: ({ children, ...props }: any) => <div data-testid="mesh-distort" {...props}>{children}</div>,
  MeshLine: ({ ...props }: any) => <div data-testid="mesh-line" {...props} />,
  MeshTransmissionMaterial: ({ ...props }: any) => <div data-testid="mesh-transmission" {...props} />,
  AccumulativeShadows: ({ children, ...props }: any) => <div data-testid="accumulative-shadows" {...props}>{children}</div>,
  RandomizedLight: ({ ...props }: any) => <div data-testid="randomized-light" {...props} />,
}));

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
  takeRecords = vi.fn();
  thresholds = [];
  root = null;
  rootMargin = '';
  scrollMargin = '';
};

// Mock auth store
vi.mock('@/lib/auth', () => ({
  useAuthStore: () => ({
    user: { id: "test-user", name: "Test User", email: "test@cauveris.ai", role: "operator" },
    token: "mock-token",
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
  }),
}));

// Shared mock for @/components/ui - comprehensive mock with ALL components from ui/index.ts
vi.mock("@/components/ui", () => ({
  // Button
  Button: ({ children, className = "", disabled, ...props }: any) => (
    <button
      className={`focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] ${className}`}
      disabled={disabled}
      aria-disabled={disabled}
      {...props}
    >{children}</button>
  ),

  // Input
  Input: ({
    className = "",
    label,
    hideLabel,
    wrapperClassName,
    hint,
    error,
    icon,
    rightElement,
    state,
    size,
    ...props
  }: any) => (
    <input className={className} {...props} />
  ),

  // Select
  Select: ({
    className = "",
    value,
    onValueChange,
    options,
    label,
    hideLabel,
    wrapperClassName,
    hint,
    error,
    size,
    state,
    ...props
  }: any) => (
    <div className={wrapperClassName}>
      {label && <label htmlFor={props.id || "select-mock"} className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1.5">{label}</label>}
      <select id={props.id || "select-mock"} className={className} value={value} onChange={(e) => onValueChange(e.target.value)} {...props}>
        {options?.map((opt: any) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
      </select>
    </div>
  ),

  // Card
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

  // Badge
  Badge: ({
    children,
    tone = "default",
    variant,
    size,
    dot,
    className = "",
    ...props
  }: any) => (
    <span
      className={`px-2 py-0.5 rounded text-xs ${className}`}
      data-tone={tone}
      data-dot={dot ? "true" : undefined}
      {...props}
    >
      {children}
    </span>
  ),

  // Tabs
  Tabs: ({ children, defaultValue, className = "", ...props }: any) => (
    <div className={className} {...props} data-testid="tabs">{children}</div>
  ),
  TabsList: ({ children, className = "", ...props }: any) => (
    <div role="tablist" className={className} {...props} data-testid="tabs-list">{children}</div>
  ),
  TabsTrigger: ({ children, value, className = "", ...props }: any) => (
    <button role="tab" className={className} data-value={value} {...props}>{children}</button>
  ),
  TabsContent: ({ children, value, className = "", ...props }: any) => (
    <div role="tabpanel" className={className} data-value={value} {...props}>{children}</div>
  ),

  // Table
  Table: ({ children, className = "", ...props }: any) => (
    <table className={className} {...props}>{children}</table>
  ),
  TableHeader: ({ children, className = "", ...props }: any) => (
    <thead className={className} {...props}>{children}</thead>
  ),
  TableBody: ({ children, className = "", ...props }: any) => (
    <tbody className={className} {...props}>{children}</tbody>
  ),
  TableRow: ({ children, className = "", ...props }: any) => (
    <tr className={className} {...props}>{children}</tr>
  ),
  TableHead: ({ children, className = "", ...props }: any) => (
    <th className={className} {...props}>{children}</th>
  ),
  TableCell: ({ children, className = "", ...props }: any) => (
    <td className={className} {...props}>{children}</td>
  ),

  // Tooltip
  Tooltip: ({ children, content }: { children: React.ReactNode; content: React.ReactNode }) => (
    <div className="relative inline-block" data-testid="tooltip">
      {children}
      <div className="absolute invisible group-hover:visible">{content}</div>
    </div>
  ),
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,

  // Dropdown
  Dropdown: ({ children, open, onOpenChange, ...props }: any) => (
    <div {...props} data-testid="dropdown">{children}</div>
  ),
  DropdownTrigger: ({ children, ...props }: any) => <button {...props}>{children}</button>,
  DropdownContent: ({ children, className = "", ...props }: any) => (
    <div className={className} {...props}>{children}</div>
  ),
  DropdownItem: ({ children, onSelect, disabled = false, ...props }: any) => (
    <div onClick={() => !disabled && onSelect?.()} className={props.className} {...props}>{children}</div>
  ),

  // Modal
  Modal: ({ children, open, onClose, ...props }: any) => (
    open ? <div role="dialog" {...props}>{children}</div> : null
  ),

  // Dialog
  Dialog: ({ children, open, ...props }: any) => (
    open ? <div role="dialog" {...props}>{children}</div> : null
  ),

  // Progress
  Progress: ({ className = "", value, ...props }: any) => (
    <div className={className} role="progressbar" aria-valuenow={value} {...props} />
  ),

  // Avatar
  Avatar: ({ src, alt, className = "", ...props }: any) => (
    <div className={className} {...props}>
      {src ? <img src={src} alt={alt} /> : <span>{alt?.charAt(0) || '?'}</span>}
    </div>
  ),

  // Divider
  Divider: ({ orientation = "horizontal", className = "", ...props }: any) => (
    orientation === "horizontal" ? (
      <hr className={`border-t border-[var(--color-border)] ${className}`} role="separator" {...props} />
    ) : (
      <div className={`border-l border-[var(--color-border)] ${className}`} role="separator" {...props} />
    )
  ),

  // Switch
  Switch: ({ checked, onChange, disabled = false, className = "", ...props }: any) => (
    <button
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      role="switch"
      aria-checked={checked}
      className={className}
      {...props}
    >
      {checked ? 'ON' : 'OFF'}
    </button>
  ),

  // Label
  Label: ({ children, className = "", ...props }: any) => (
    <label className={className} {...props}>{children}</label>
  ),

  // Toolbar
  Toolbar: ({ children, className = "", ...props }: any) => (
    <div role="toolbar" className={className} {...props}>{children}</div>
  ),
  ToolbarGroup: ({ children, className = "", ...props }: any) => (
    <div className={className} {...props}>{children}</div>
  ),
  ToolbarItem: ({ children, className = "", ...props }: any) => (
    <div className={className} {...props}>{children}</div>
  ),
  ToolbarTitle: ({ children, className = "", ...props }: any) => (
    <span className={className} {...props}>{children}</span>
  ),
  ToolbarSpacer: ({ className = "", ...props }: any) => (
    <div className={className} {...props} />
  ),
  ToolbarSeparator: ({ className = "", ...props }: any) => (
    <div role="separator" className={className} {...props} />
  ),

  // PageHeader
  PageHeader: ({ title, subtitle, badge, actions, ...props }: any) => (
    <div className="mb-8" {...props}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="text-gradient text-3xl font-bold tracking-tight">{title}</h1>
          {badge}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {subtitle && <p className="mt-1.5 text-sm text-[var(--color-text-muted)]">{subtitle}</p>}
    </div>
  ),

  // EmptyState
  EmptyState: ({ title, description, ...props }: any) => (
    <div {...props}><h3>{title}</h3><p>{description}</p></div>
  ),
  EmptyStateIcons: {},

  // Skeleton
  Skeleton: ({ className = "", ...props }: any) => (
    <div className={className} {...props} />
  ),

  // Box
  Box: ({ children, className = "", ...props }: any) => (
    <div className={className} {...props}>{children}</div>
  ),

  // ActionList
  ActionList: ({ children, className = "", ...props }: any) => (
    <div className={className} {...props}>{children}</div>
  ),

  // Stat
  Stat: ({ label, value, sub, trend, ...props }: any) => (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]/40 p-4" {...props}>
      <div className="text-[11px] font-medium uppercase tracking-wider text-[var(--color-text-muted)]">{label}</div>
      <div className="mt-1.5 font-mono text-2xl font-semibold text-[var(--color-text-primary)]">{value}</div>
      {sub && <div className={`mt-1 text-xs`}>{sub}</div>}
    </div>
  ),

  // KV
  KV: ({ label, value, sub, ...props }: any) => (
    <div className="flex items-center justify-between gap-4 py-2 text-sm" {...props}>
      <div>
        <span className="text-[var(--color-text-muted)]">{label}</span>
        {sub && <span className="block text-sm text-[var(--color-text-muted)]/70">{sub}</span>}
      </div>
      <span className="text-right font-medium text-[var(--color-text-primary)]">{value}</span>
    </div>
  ),

  // Toggle
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

  // NEW: Slider components
  Slider: ({ className = "", value, min = 0, max = 100, step = 1, onValueChange, showValue, valueFormatter, disabled = false, "aria-label": ariaLabel, ...props }: any) => (
    <div className={className} {...props}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onValueChange?.(Number(e.target.value))}
        disabled={disabled}
        aria-label={ariaLabel}
      />
      {showValue && <span data-testid="slider-value">{valueFormatter ? valueFormatter(value) : value}</span>}
    </div>
  ),
  RangeSlider: ({ className = "", value = [0, 100], min = 0, max = 100, step = 1, onValueChange, showValue, valueFormatter, disabled = false, "aria-label": ariaLabel, ...props }: any) => (
    <div className={className} {...props}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value[0]}
        onChange={(e) => onValueChange?.([Number(e.target.value), value[1]])}
        disabled={disabled}
        aria-label={ariaLabel}
      />
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value[1]}
        onChange={(e) => onValueChange?.([value[0], Number(e.target.value)])}
        disabled={disabled}
        aria-label={ariaLabel}
      />
      {showValue && <span data-testid="slider-value">{valueFormatter ? valueFormatter(value) : `${value[0]} - ${value[1]}`}</span>}
    </div>
  ),
  MarkedSlider: ({ className = "", value, min = 0, max = 100, step = 1, marks = [], onValueChange, showValue, valueFormatter, disabled = false, "aria-label": ariaLabel, ...props }: any) => (
    <div className={className} {...props}>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onValueChange?.(Number(e.target.value))}
        disabled={disabled}
        aria-label={ariaLabel}
      />
      {showValue && <span data-testid="slider-value">{valueFormatter ? valueFormatter(value) : value}</span>}
      <div className="flex justify-between mt-2 text-[10px] text-[var(--color-fg-muted)]">
        {marks.map((mark: any, i: number) => (
          <span key={i} style={{ left: `${(mark / max) * 100}%` }}>{mark}</span>
        ))}
      </div>
    </div>
  ),

  // NEW: Panel components
  Panel: ({ children, className = "", title, subtitle, headerActions, headerDivider, footer, footerDivider, ...props }: any) => (
    <div className={className} {...props}>
      {title && <h2 data-testid="panel-title">{title}</h2>}
      {subtitle && <p data-testid="panel-subtitle">{subtitle}</p>}
      {headerActions && <div data-testid="panel-header-actions">{headerActions}</div>}
      {headerDivider && <hr data-testid="panel-header-divider" />}
      <div data-testid="panel-content">{children}</div>
      {footerDivider && <hr data-testid="panel-footer-divider" />}
      {footer && <footer data-testid="panel-footer">{footer}</footer>}
    </div>
  ),
  PanelSection: ({ children, className = "", title, subtitle, dividerBefore, ...props }: any) => (
    <div className={className} {...props}>
      {dividerBefore && <hr data-testid="panel-section-divider" />}
      {title && <h3 data-testid="panel-section-title">{title}</h3>}
      {subtitle && <p data-testid="panel-section-subtitle">{subtitle}</p>}
      <div data-testid="panel-section-content">{children}</div>
    </div>
  ),
  PanelStack: ({ children, className = "", space = "md", ...props }: any) => (
    <div className={className} {...props} data-testid="panel-stack">{children}</div>
  ),
  PanelCard: ({ children, className = "", title, subtitle, leading, trailing, hoverable, selected, onClick, ...props }: any) => (
    <div className={className} onClick={onClick} {...props} data-testid="panel-card">
      {leading && <div data-testid="panel-card-leading">{leading}</div>}
      <div data-testid="panel-card-body">
        {title && <h3 data-testid="panel-card-title">{title}</h3>}
        {subtitle && <div data-testid="panel-card-subtitle">{subtitle}</div>}
        {trailing && <div data-testid="panel-card-trailing">{trailing}</div>}
        {children && <div data-testid="panel-card-children">{children}</div>}
      </div>
    </div>
  ),
  PanelDivider: ({ label, className = "", ...props }: any) => (
    <div className={className} {...props} data-testid="panel-divider">
      {label && <span data-testid="panel-divider-label">{label}</span>}
    </div>
  ),
  PanelHeader: ({ title, subtitle, actions, divider, className = "", ...props }: any) => (
    <div className={className} {...props} data-testid="panel-header">
      <div data-testid="panel-header-title">
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div data-testid="panel-header-actions">{actions}</div>}
      {divider && <hr />}
    </div>
  ),
  PanelFooter: ({ children, className = "", divider, align = "end", ...props }: any) => (
    <div className={className} {...props} data-testid="panel-footer">
      {divider && <hr />}
      {children}
    </div>
  ),
}));