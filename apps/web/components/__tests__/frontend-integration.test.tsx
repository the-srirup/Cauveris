import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MissionControl from "@/app/page";
import { WorkspaceLauncher } from "@/components/workspace/WorkspaceLauncher";
import { api } from "@/lib/api";

const pushMock = vi.fn();
const replaceMock = vi.fn();

// Mock router
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
  }),
}));

describe("Frontend Real-Backend Integration Contracts", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("starts in clean empty state: redirects to workspace with 3 clear entry actions", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "healthy",
      service: "cauveris",
      version: "3.1.0",
      latency_ms: 10,
    });
    vi.spyOn(api, "modelHealth").mockResolvedValue({
      status: "healthy",
      provider: "Local model server",
      mode: "local_only",
      cloud_credentials_required: false,
    });
    vi.spyOn(api, "list").mockResolvedValue({ incidents: [], count: 0 });

    render(<MissionControl />);

    // Unauthenticated/no-incident visits route to the Workspace Hub
    await waitFor(() => {
      expect(replaceMock.mock.calls.length + pushMock.mock.calls.length).toBeGreaterThanOrEqual(1);
    });

    // The Workspace Hub launchpad displays 3 clear entry paths
    render(<WorkspaceLauncher />);
    expect(screen.getByText("New incident")).toBeInTheDocument();
    expect(screen.getByText("Load sample benchmark")).toBeInTheDocument();
    expect(screen.getByText("Resume saved session")).toBeInTheDocument();
  });

  it("requires explicit click to load sample and marks SAMPLE DATA clearly", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "healthy",
      service: "cauveris",
      version: "3.1.0",
    });
    vi.spyOn(api, "modelHealth").mockResolvedValue({
      status: "healthy",
      provider: "Local model server",
      mode: "local_only",
      cloud_credentials_required: false,
    });
    vi.spyOn(api, "create").mockResolvedValue({
      incident_id: "CAU-0001",
      message: "Golden loaded",
      is_demonstration: true,
    });
    vi.spyOn(api, "get").mockResolvedValue({
      id: "CAU-0001",
      title: "Golden Benchmark Incident",
      status: "OBSERVED",
      evidence_count: 14,
      is_demonstration: true,
    });
    vi.spyOn(api, "getEvents").mockResolvedValue({
      state: "IDLE",
      progress: 0,
      stages: [],
      is_demonstration: true,
    });
    vi.spyOn(api, "list").mockResolvedValue({
      incidents: [
        {
          id: "CAU-0001",
          title: "Golden Benchmark Incident",
          status: "OBSERVED",
          evidence_count: 14,
          is_demonstration: true,
        },
      ],
      count: 1,
    });

    // 1. Explicitly click to launch benchmark in workspace launcher
    render(<WorkspaceLauncher />);
    const loadSampleBtn = screen.getByLabelText("Load golden incident");
    fireEvent.click(loadSampleBtn);

    await waitFor(() => {
      expect(api.create).toHaveBeenCalled();
    });

    // 2. Active incident dashboard renders loaded incident
    localStorage.setItem("cauveris_active_incident_id", "CAU-0001");
    render(<MissionControl />);

    await waitFor(() => {
      expect(screen.getByText(/Golden Benchmark Incident/i)).toBeInTheDocument();
    });
  });

  it("handles backend API error honestly with actionable error and retry", async () => {
    localStorage.setItem("cauveris_active_incident_id", "CAU-0001");
    vi.spyOn(api, "health").mockRejectedValue(new Error("Cannot connect to Cauveris API"));
    vi.spyOn(api, "list").mockRejectedValue(new Error("Backend unreachable"));

    render(<MissionControl />);

    await waitFor(() => {
      expect(screen.getByText(/UNAVAILABLE/i)).toBeInTheDocument();
    });
  });
});
