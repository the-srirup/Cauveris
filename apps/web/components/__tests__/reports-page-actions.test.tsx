import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import ReportsPage, { ReportPage } from "@/app/reports/page";

const mockAddActivity = vi.fn();
const mockSetIncidentContext = vi.fn();

// Reports as the backend /incidents/{id}/reports endpoint returns them —
// the page no longer fabricates a local report inventory. `vi.hoisted` keeps
// this available to the hoisted `vi.mock` factory below.
const { apiReports } = vi.hoisted(() => ({
  apiReports: [

  {
    id: "report-investigation",
    incident_id: "CAU-0001",
    title: "Full Investigation Report",
    generated_at: "2026-10-23T00:00:00Z",
    size_bytes: 20480,
    format: "json",
    status: "ready",
    type: "investigation",
  },
  {
    id: "report-executive",
    incident_id: "CAU-0001",
    title: "Executive Summary",
    generated_at: "2026-10-23T00:05:00Z",
    size_bytes: 8192,
    format: "pdf",
    status: "ready",
    type: "executive",
  },
  {
    id: "report-technical",
    incident_id: "CAU-0001",
    title: "Technical Deep Dive",
    generated_at: "2026-10-23T00:10:00Z",
    size_bytes: 12288,
    format: "json",
    status: "ready",
    type: "technical",
  },
  ],
}));

vi.mock("@/lib/api", () => ({
  api: {
    listReports: vi.fn().mockResolvedValue({ reports: apiReports }),
    getReport: vi.fn().mockResolvedValue({
      incident_id: "CAU-0001",
      title: "Full Investigation Report",
      description: "Robot consumes stale object detections",
      status: "ready",
      system_name: "warehouse-amr-01",
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
    reconstruct: vi.fn().mockResolvedValue({ status: "started" }),
    deleteReport: vi.fn().mockResolvedValue({ message: "Report deleted" }),
  },
}));

import { api } from "@/lib/api";
const mockedListReports = vi.mocked(api.listReports);
const mockGetReport = vi.mocked(api.getReport);
const mockReconstruct = vi.mocked(api.reconstruct);

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
    },
    addActivity: mockAddActivity,
    setIncidentContext: mockSetIncidentContext,
    setActiveNav: vi.fn(),
  }),
}));

const mockIncident = {
  id: "CAU-0001",
  title: "Warehouse robot emergency stop",
  system_name: "warehouse-amr-01",
  description: "Robot consumes stale object detections",
  approximate_time: "2026-09-20T10:30:00Z",
  evidence_count: 18,
  required_evidence_count: 14,
  missing_required_evidence: [],
};

vi.mock("@/lib/useIncident", () => ({
  useActiveIncident: () => ({
    incident: mockIncident,
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
    mockedListReports.mockResolvedValue({ reports: apiReports });
    mockGetReport.mockResolvedValue({
      incident_id: "CAU-0001",
      title: "Full Investigation Report",
      description: "Robot consumes stale object detections",
      status: "ready",
      system_name: "warehouse-amr-01",
      hypotheses: [],
      evidence_summary: {
        total_evidence_items: 18,
        required_evidence_items: 14,
        missing_required_evidence: [],
      },
    });
    mockReconstruct.mockResolvedValue({ status: "started" });
    global.URL.createObjectURL = vi.fn(() => "blob:http://localhost/test-blob");
    global.URL.revokeObjectURL = vi.fn();
  });

  it("exports both default ReportsPage and named ReportPage", () => {
    expect(ReportsPage).toBeDefined();
    expect(ReportPage).toBeDefined();
  });

  it("loads the report inventory from the API and renders action buttons for each report", async () => {
    render(<ReportsPage />);

    await waitFor(() => {
      expect(mockedListReports).toHaveBeenCalledWith("CAU-0001");
    });

    const table = await screen.findByRole("table");
    expect(table).toBeInTheDocument();
    expect(within(table).getByText("report-investigation")).toBeInTheDocument();
    expect(within(table).getByText("report-executive")).toBeInTheDocument();
    expect(within(table).getByText("report-technical")).toBeInTheDocument();

    const viewButtons = screen.getAllByRole("button", { name: /view report/i });
    const downloadButtons = screen.getAllByRole("button", { name: /download report/i });
    const deleteButtons = screen.getAllByRole("button", { name: /delete report/i });

    expect(viewButtons.length).toBe(3);
    expect(downloadButtons.length).toBe(3);
    expect(deleteButtons.length).toBe(3);
  });

  it("shows the honest empty state when the backend reports no reports", async () => {
    mockedListReports.mockResolvedValue({ reports: [] });
    render(<ReportsPage />);

    expect(await screen.findByText(/no reports found/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("Eye icon (View) opens the report details modal with tabs and content", async () => {
    render(<ReportsPage />);

    const firstViewBtn = (await screen.findAllByRole("button", { name: /view report/i }))[0];
    fireEvent.click(firstViewBtn);

    await waitFor(() => {
      expect(mockGetReport).toHaveBeenCalledWith("CAU-0001");
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

    const firstDownloadBtn = (await screen.findAllByRole("button", { name: /download report/i }))[0];
    fireEvent.click(firstDownloadBtn);

    await waitFor(() => {
      expect(mockGetReport).toHaveBeenCalledWith("CAU-0001");
      expect(global.URL.createObjectURL).toHaveBeenCalled();
      expect(mockAddActivity).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "system",
          message: expect.stringMatching(/downloaded/i),
        })
      );
    });
  });

  it("Download surfaces a backend error honestly when the report is not yet generated", async () => {
    mockGetReport.mockRejectedValueOnce(
      new Error("Report not yet generated on the server — run the investigation pipeline first")
    );
    render(<ReportsPage />);

    const firstDownloadBtn = (await screen.findAllByRole("button", { name: /download report/i }))[0];
    fireEvent.click(firstDownloadBtn);

    await waitFor(() => {
      expect(mockAddActivity).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "error",
          message: expect.stringMatching(/not yet generated/i),
        })
      );
    });
    expect(global.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("Generate Report triggers pipeline reconstruction and refreshes the report inventory", async () => {
    render(<ReportsPage />);

    await screen.findByRole("table");
    const generateBtn = screen.getByRole("button", { name: /generate report/i });
    fireEvent.click(generateBtn);

    await waitFor(() => {
      expect(mockReconstruct).toHaveBeenCalledWith("CAU-0001");
      expect(mockedListReports).toHaveBeenCalledTimes(2);
    });
  });

  it("Delete icon opens confirmation dialog and deletes the report upon confirmation", async () => {
    render(<ReportsPage />);

    expect(await screen.findByText("report-executive")).toBeInTheDocument();

    const deleteButtons = screen.getAllByRole("button", { name: /delete report/i });
    fireEvent.click(deleteButtons[1]);

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
    expect(screen.getByText(/delete report/i, { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText(/are you sure you want to delete/i)).toBeInTheDocument();

    const confirmDeleteBtn = screen.getByRole("button", { name: /^delete report$/i });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
      expect(screen.queryByText("report-executive")).not.toBeInTheDocument();
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

    expect(await screen.findByText("report-investigation")).toBeInTheDocument();

    const firstDeleteBtn = screen.getAllByRole("button", { name: /delete report/i })[0];
    fireEvent.click(firstDeleteBtn);

    expect(screen.getByRole("alertdialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByText("report-investigation")).toBeInTheDocument();
  });

  it("Report Templates component renders all 4 templates and handles preview modal and actions", async () => {
    render(<ReportsPage />);

    // Wait for reports to load
    await screen.findByRole("table");

    // Check that Report Templates section exists
    expect(screen.getByRole("heading", { name: /report templates/i, level: 2 })).toBeInTheDocument();

    // Verify all 4 template titles
    expect(screen.getByRole("heading", { name: /^full investigation$/i, level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^executive summary$/i, level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^technical deep dive$/i, level: 3 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^compliance & audit$/i, level: 3 })).toBeInTheDocument();

    // Investigation, Executive, and Technical reports exist in apiReports mock, so they show Inspect buttons
    const inspectBtn = screen.getByRole("button", { name: /inspect full investigation document/i });
    expect(inspectBtn).toBeInTheDocument();

    // Clicking Inspect opens the viewer modal
    fireEvent.click(inspectBtn);
    await waitFor(() => {
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /close report viewer/i }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    // Compliance report does NOT exist in apiReports mock, so it shows Create Document and Preview Spec buttons
    const previewComplianceBtn = screen.getByRole("button", { name: /preview compliance & audit template specification/i });
    expect(previewComplianceBtn).toBeInTheDocument();

    // Click Preview Spec to open the template preview modal
    fireEvent.click(previewComplianceBtn);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /template: compliance & audit/i, level: 3 })).toBeInTheDocument();
    expect(screen.getByText(/specification & structure/i)).toBeInTheDocument();
    expect(screen.getByText(/sample output excerpt/i)).toBeInTheDocument();

    // Switch to sample tab
    fireEvent.click(screen.getByText(/sample output excerpt/i));
    expect(screen.getByText(/compliance & security audit verification/i)).toBeInTheDocument();

    // Close preview modal
    fireEvent.click(screen.getByRole("button", { name: /close preview/i }));
    expect(screen.queryByRole("heading", { name: /template: compliance & audit/i, level: 3 })).not.toBeInTheDocument();
  });
});
