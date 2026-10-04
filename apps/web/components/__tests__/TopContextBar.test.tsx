import { render, screen, fireEvent } from "@testing-library/react";
import * as React from "react";
import { vi, describe, it, expect } from "vitest";

// Mock lucide-react icons
vi.mock('lucide-react', () => ({
  Zap: (props: any) => <svg data-testid="icon-zap" {...props} />,
  Database: (props: any) => <svg data-testid="icon-database" {...props} />,
  GitBranch: (props: any) => <svg data-testid="icon-git-branch" {...props} />,
  FlaskConical: (props: any) => <svg data-testid="icon-flask" {...props} />,
  Wrench: (props: any) => <svg data-testid="icon-wrench" {...props} />,
  Eye: (props: any) => <svg data-testid="icon-eye" {...props} />,
  FileText: (props: any) => <svg data-testid="icon-file-text" {...props} />,
  RotateCcw: (props: any) => <svg data-testid="icon-rotate-ccw" {...props} />,
  Download: (props: any) => <svg data-testid="icon-download" {...props} />,
  AlertTriangle: (props: any) => <svg data-testid="icon-alert-triangle" {...props} />,
  Plus: (props: any) => <svg data-testid="icon-plus" {...props} />,
  Upload: (props: any) => <svg data-testid="icon-upload" {...props} />,
  Play: (props: any) => <svg data-testid="icon-play" {...props} />,
  Square: (props: any) => <svg data-testid="icon-square" {...props} />,
  ExternalLink: (props: any) => <svg data-testid="icon-external-link" {...props} />,
  Clock: (props: any) => <svg data-testid="icon-clock" {...props} />,
  ChevronRight: (props: any) => <svg data-testid="icon-chevron-right" {...props} />,
  ChevronLeft: (props: any) => <svg data-testid="icon-chevron-left" {...props} />,
  Menu: (props: any) => <svg data-testid="icon-menu" {...props} />,
  X: (props: any) => <svg data-testid="icon-x" {...props} />,
  LayoutDashboard: (props: any) => <svg data-testid="icon-layout-dashboard" {...props} />,
  Search: (props: any) => <svg data-testid="icon-search" {...props} />,
  Bot: (props: any) => <svg data-testid="icon-bot" {...props} />,
  Scale: (props: any) => <svg data-testid="icon-scale" {...props} />,
  Shield: (props: any) => <svg data-testid="icon-shield" {...props} />,
  Link: (props: any) => <svg data-testid="icon-link" {...props} />,
  Check: (props: any) => <svg data-testid="icon-check" {...props} />,
  HelpCircle: (props: any) => <svg data-testid="icon-help-circle" {...props} />,
  Info: (props: any) => <svg data-testid="icon-info" {...props} />,
  Loader2: (props: any) => <svg data-testid="icon-loader-2" {...props} />,
  Terminal: (props: any) => <svg data-testid="icon-terminal" {...props} />,
  WifiOff: (props: any) => <svg data-testid="icon-wifi-off" {...props} />,
  AlertCircle: (props: any) => <svg data-testid="icon-alert-circle" {...props} />,
  CheckCircle: (props: any) => <svg data-testid="icon-check-circle" {...props} />,
  XCircle: (props: any) => <svg data-testid="icon-x-circle" {...props} />,
  ChevronUp: (props: any) => <svg data-testid="icon-chevron-up" {...props} />,
  ChevronDown: (props: any) => <svg data-testid="icon-chevron-down" {...props} />,
  Filter: (props: any) => <svg data-testid="icon-filter" {...props} />,
  Trash2: (props: any) => <svg data-testid="icon-trash-2" {...props} />,
  User: (props: any) => <svg data-testid="icon-user" {...props} />,
  LogOut: (props: any) => <svg data-testid="icon-logout" {...props} />,
}));

// Mock all dependencies before importing the component
vi.mock("@/lib/useShell", () => ({
  useShell: () => ({
    state: {
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
    },
    setIncidentContext: vi.fn(),
    addActivity: vi.fn(),
    toggleCommandPalette: vi.fn(),
  }),
  ShellProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@/lib/useIncident", () => ({
  useActiveIncident: () => ({
    incident: { id: "CAU-0001", title: "Test Incident" },
    judgeMode: false,
    engineerMode: false,
    loadIncident: vi.fn(),
  }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    create: vi.fn(),
    reconstruct: vi.fn(),
    cancel: vi.fn(),
    exportReport: vi.fn(),
    resetDemo: vi.fn(),
  },
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
}));

// Import after mocks
import { TopContextBar } from "@/components/TopContextBar";
import { ShellProvider } from "@/lib/useShell";

describe("TopContextBar", () => {
  it("renders incident ID and title", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByText("CAU-0001")).toBeInTheDocument();
    expect(screen.getByText("Test Incident")).toBeInTheDocument();
  });

  it("shows incident state badge", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByText("RUNNING")).toBeInTheDocument();
  });

  it("shows pipeline stage pill", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByText("INGEST")).toBeInTheDocument();
  });

  it("shows evidence coverage progress ring", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    // Progress ring is an SVG, check for aria-valuenow
    const progress = screen.getByRole("progressbar");
    expect(progress).toHaveAttribute("aria-valuenow", "75");
  });

  it("shows processing mode badge", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByText("Autonomous")).toBeInTheDocument();
  });

  it("shows model provider and backend status", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByText("Local Fixtures")).toBeInTheDocument();
    expect(screen.getByText("online")).toBeInTheDocument();
  });

  it("renders global action buttons", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByLabelText("Create new incident")).toBeInTheDocument();
    expect(screen.getByLabelText("Load golden incident")).toBeInTheDocument();
    expect(screen.getByLabelText("Upload evidence bundle")).toBeInTheDocument();
    expect(screen.getByLabelText("Open command palette")).toBeInTheDocument();
  });

  it("shows command palette button", () => {
    render(
      <ShellProvider>
        <TopContextBar />
      </ShellProvider>
    );
    expect(screen.getByLabelText("Open command palette")).toBeInTheDocument();
  });
});