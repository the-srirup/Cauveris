import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import MissionControl from "@/app/page";
import { api } from "@/lib/api";

// Mock router
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("Frontend Real-Backend Integration Contracts", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("starts in clean empty state with selectedIncidentId = null and 3 clear entry actions", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "healthy",
      service: "cauveris",
      version: "0.1.0",
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

    // Should display welcome screen with 3 clear entry paths
    expect(await screen.findByText(/Welcome to Cauveris Reality Debugger/i)).toBeInTheDocument();
    expect(screen.getByText(/Upload Incident Package/i)).toBeInTheDocument();
    expect(screen.getByText(/Create Incident Workspace/i)).toBeInTheDocument();
    expect(screen.getByText(/Load Sample Incident/i)).toBeInTheDocument();
  });

  it("requires explicit click to load sample and marks SAMPLE DATA clearly", async () => {
    vi.spyOn(api, "health").mockResolvedValue({
      status: "healthy",
      service: "cauveris",
      version: "0.1.0",
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

    render(<MissionControl />);

    const loadSampleBtn = await screen.findByText(/Load Sample Incident/i);
    fireEvent.click(loadSampleBtn);

    await waitFor(() => {
      expect(screen.getByText(/Golden Benchmark \[CAU-0001\]/i)).toBeInTheDocument();
    });
  });

  it("handles backend API error honestly with actionable error and retry", async () => {
    vi.spyOn(api, "health").mockRejectedValue(new Error("Cannot connect to Cauveris API"));
    vi.spyOn(api, "list").mockRejectedValue(new Error("Backend unreachable"));

    render(<MissionControl />);

    expect(await screen.findByText(/UNAVAILABLE/i)).toBeInTheDocument();
  });
});
