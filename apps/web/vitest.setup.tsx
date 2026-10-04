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

// Mock lucide-react - just provide basic icons
vi.mock('lucide-react', () => {
  // Create a mock icon component
  const createMockIcon = (name: string) => {
    return (props: any) => <svg data-testid={`icon-${name}`} {...props} />;
  };

  return {
    Zap: createMockIcon('Zap'),
    Database: createMockIcon('Database'),
    GitBranch: createMockIcon('GitBranch'),
    FlaskConical: createMockIcon('FlaskConical'),
    Wrench: createMockIcon('Wrench'),
    Eye: createMockIcon('Eye'),
    FileText: createMockIcon('FileText'),
    RotateCcw: createMockIcon('RotateCcw'),
    Download: createMockIcon('Download'),
    AlertTriangle: createMockIcon('AlertTriangle'),
    Plus: createMockIcon('Plus'),
    Upload: createMockIcon('Upload'),
    Play: createMockIcon('Play'),
    Square: createMockIcon('Square'),
    ExternalLink: createMockIcon('ExternalLink'),
    Clock: createMockIcon('Clock'),
    ChevronRight: createMockIcon('ChevronRight'),
    ChevronLeft: createMockIcon('ChevronLeft'),
    Menu: createMockIcon('Menu'),
    X: createMockIcon('X'),
    LayoutDashboard: createMockIcon('LayoutDashboard'),
    Search: createMockIcon('Search'),
    Bot: createMockIcon('Bot'),
    Scale: createMockIcon('Scale'),
    Shield: createMockIcon('Shield'),
    Link: createMockIcon('Link'),
    Check: createMockIcon('Check'),
    HelpCircle: createMockIcon('HelpCircle'),
    Info: createMockIcon('Info'),
    Loader2: createMockIcon('Loader2'),
    Terminal: createMockIcon('Terminal'),
    WifiOff: createMockIcon('WifiOff'),
    AlertCircle: createMockIcon('AlertCircle'),
    CheckCircle: createMockIcon('CheckCircle'),
    XCircle: createMockIcon('XCircle'),
    ChevronUp: createMockIcon('ChevronUp'),
    ChevronDown: createMockIcon('ChevronDown'),
    Filter: createMockIcon('Filter'),
    Trash2: createMockIcon('Trash2'),
    Settings: createMockIcon('Settings'),
    Palette: createMockIcon('Palette'),
    Bell: createMockIcon('Bell'),
    Moon: createMockIcon('Moon'),
    Sun: createMockIcon('Sun'),
    Monitor: createMockIcon('Monitor'),
    Globe: createMockIcon('Globe'),
  };
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
vi.mock('@/lib/api', () => ({
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