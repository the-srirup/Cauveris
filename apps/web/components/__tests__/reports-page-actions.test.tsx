import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import ReportsPage, { ReportPage } from "@/app/reports/page";

const mockAddActivity = vi.fn();
const mockSetIncidentContext = vi.fn();

vi.mock("@/lib/api", () => ({
  api: {
    listReports: vi.fn().mockResolvedValue({ reports: [] }),
    getReport: vi.fn().mockResolvedValue({
      title: "Full Investigation Report",
      description: "Robot consumes stale object detections",
      status: "COMPLETED",
      hypotheses: [
        {
          hypothesis_id: "H1",
          causal_claim: "Dynamic batching window parameter increase in deployment v42 caused queue starvation",
          status: "CONFIRMED",
          confidence_posterior: 0.98,
        },
      ],
      evidence_summary: {
        total_evidence_items: 18,
        required_evidence_items: 14,
        missing_required_evidence: [],
      },
    }),
    exportReport: vi.fn().mockResolvedValue({
      incident_id: "CAU-0001",
      title: "Full Investigation Report",
    }),
    deleteReport: vi.fn().mockResolvedValue({ message: "Report deleted" }),
  },
}));

vi.mock("@/lib/useShell", () => ({
  useShell: () => ({
    state: {
      activeNav: "reports",
      isNavCollapsed: false,
      isNavDrawerOpen: false,
      incidentContext: null,
      inspectorOpen: false,
      inspectorMode: null,
      inspectorData: { mode: null },
      trayState: "compact",
      activities: [],
      commandPaletteOpen: false,
    },
    addActivity: mockAddActivity,
    setIncidentContext: mockSetIncidentContext,
    setActiveNav: vi.fn(),
  }),
}));

vi.mock("@/lib/useIncident", () => ({
  useActiveIncident: () => ({
    incident: {
      id: "CAU-0001",
      title: "Warehouse robot emergency stop",
      system_name: "warehouse-amr-01",
      description: "Robot consumes stale object detections",
      approximate_time: "2026-09-20T10:30:00Z",
      evidence_count: 18,
      required_evidence_count: 14,
      missing_required_evidence: [],
    },
    incidentId: "CAU-0001",
    judgeMode: false,
    engineerMode: false,
    loadIncident: vi.fn(),
    setIncidentId: vi.fn(),
  }),
}));

describe("ReportsPage - Action Buttons Functionality", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.URL.createObjectURL = vi.fn(() => "blob:http://localhost/test-blob");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("exports both default ReportsPage and named ReportPage", () => {
    expect(ReportsPage).toBeDefined();
    expect(ReportPage).toBeDefined();
  });

  it("renders reports table with Eye, Download, and Delete buttons for each report", async () => {
    render(<ReportsPage />);

    expect(screen.getByText("Reports")).toBeInTheDocument();

    const table = screen.getByRole("table");
    expect(table).toBeInTheDocument();
    expect(within(table).getByText("rpt-001")).toBeInTheDocument();
    expect(within(table).getByText("rpt-002")).toBeInTheDocument();

    const viewButtons = screen.getAllByRole("button", { name: /view report/i });
    const downloadButtons = screen.getAllByRole("button", { name: /download report/i });
    const deleteButtons = screen.getAllByRole("button", { name: /delete report/i });

    expect(viewButtons.length).toBeGreaterThanOrEqual(3);
    expect(downloadButtons.length).toBeGreaterThanOrEqual(3);
    expect(deleteButtons.length).toBeGreaterThanOrEqual(3);
  });

  it("Eye icon (View) opens the report details modal with tabs and content", async () => {
    render(<ReportsPage />);

    expect(screen.getByText("rpt-001")).toBeInTheDocument();

    const firstViewBtn = screen.getAllByRole("button", { name: /view report/i })[0];
    fireEvent.click(firstViewBtn);

    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /full investigation report/i, level: 2 })).toBeInTheDocument();
    });

    expect(screen.getByText(/summary & findings/i)).toBeInTheDocument();
    expect(screen.getByText(/formatted document/i)).toBeInTheDocument();
    expect(screen.getByText(/raw json data/i)).toBeInTheDocument();

    fireEvent.click(screen.getByText(/raw json data/i));
    expect(screen.getByRole("button", { name: /copy json/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close report viewer/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("Download icon downloads the report file and logs system activity", async () => {
    render(<ReportsPage />);

    expect(screen.getByText("rpt-001")).toBeInTheDocument();

    const firstDownloadBtn = screen.getAllByRole("button", { name: /download report/i })[0];
    fireEvent.click(firstDownloadBtn);

    await waitFor(() => {
      expect(global.URL.createObjectURL).toHaveBeenCalled();
      expect(mockAddActivity).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "system",
          message: expect.stringMatching(/downloaded/i),
        })
      );
    });
  });

  it("Delete icon opens confirmation dialog and deletes the report upon confirmation", async () => {
    render(<ReportsPage />);

    expect(screen.getByText("rpt-002")).toBeInTheDocument();

    const deleteButtons = screen.getAllByRole("button", { name: /delete report/i });
    fireEvent.click(deleteButtons[1]);

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(/delete report/i, { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText(/are you sure you want to delete/i)).toBeInTheDocument();

    const confirmDeleteBtn = screen.getByRole("button", { name: /^delete report$/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      expect(screen.queryByText("rpt-002")).not.toBeInTheDocument();
      expect(mockAddActivity).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "system",
          message: expect.stringMatching(/deleted successfully/i),
        })
      );
    });
  });

  it("Delete can be cancelled without deleting", async () => {
    render(<ReportsPage />);

    expect(screen.getByText("rpt-001")).toBeInTheDocument();

    const firstDeleteBtn = screen.getAllByRole("button", { name: /delete report/i })[0];
    fireEvent.click(firstDeleteBtn);

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("rpt-001")).toBeInTheDocument();
  });
});
