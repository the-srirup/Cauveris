import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import * as React from "react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { IntakePanel } from "../IntakePanel";
import { api } from "@/lib/api";

// Mock api
vi.mock("@/lib/api", () => ({
  api: {
    ingestFromSource: vi.fn(),
    getIngestJob: vi.fn(),
    getIngestCapabilities: vi.fn(),
  },
}));

describe("IntakePanel Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the input and action buttons", () => {
    render(<IntakePanel />);
    expect(screen.getByRole("textbox", { name: /Universal source specification or URL/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Ingest$/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Show supported formats/i })).toBeInTheDocument();
  });

  it("triggers ingestion and polls job to completion", async () => {
    const mockOnSuccess = vi.fn();
    (api.ingestFromSource as any).mockResolvedValueOnce({
      job_id: "job-123",
      incident_id: "INC-TEST01",
      status: "queued",
      source_kind: "pypi",
    });

    (api.getIngestJob as any).mockResolvedValueOnce({
      job_id: "job-123",
      status: "completed",
      result: {
        incident_id: "INC-TEST01",
        package_sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        evidence_count: 42,
        warnings: [],
        source: {
          payload_kind: "tar.gz",
          sha256: "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        },
      },
    });

    render(<IntakePanel onIngestSuccess={mockOnSuccess} />);

    const input = screen.getByRole("textbox", { name: /Universal source specification or URL/i });
    fireEvent.change(input, { target: { value: "pypi:requests@2.32.3" } });

    const ingestBtn = screen.getByRole("button", { name: /^Ingest$/i });
    fireEvent.click(ingestBtn);

    expect(api.ingestFromSource).toHaveBeenCalledWith("pypi:requests@2.32.3");

    await waitFor(() => {
      expect(screen.getByText(/Ingested INC-TEST01/i)).toBeInTheDocument();
    });

    expect(mockOnSuccess).toHaveBeenCalledWith(
      expect.objectContaining({
        incident_id: "INC-TEST01",
        evidence_count: 42,
      })
    );
  });

  it("displays error message if ingestion fails", async () => {
    (api.ingestFromSource as any).mockRejectedValueOnce(new Error("URL host blocked by SSRF policy"));

    render(<IntakePanel />);

    const input = screen.getByRole("textbox", { name: /Universal source specification or URL/i });
    fireEvent.change(input, { target: { value: "https://192.168.1.1/bundle.zip" } });

    const ingestBtn = screen.getByRole("button", { name: /^Ingest$/i });
    fireEvent.click(ingestBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("URL host blocked by SSRF policy");
    });
  });

  it("toggles supported formats disclosure and fetches capabilities", async () => {
    (api.getIngestCapabilities as any).mockResolvedValueOnce({
      url_ingestion_enabled: true,
      allow_local_path_ingest: false,
      allow_git_clone: true,
      spec_forms: [
        { form: "pypi:pkg@ver", example: "pypi:requests@2.32.3", description: "PyPI package" },
        { form: "crates:name@v", example: "crates:serde@1.0.200", description: "crates.io crate" },
      ],
      supported_archive_formats: ["zip", "tar.gz", "tar.xz"],
      limits: {
        max_download_size: 50 * 1024 * 1024,
        max_archive_uncompressed_size: 200 * 1024 * 1024,
        max_archive_members: 1000,
      },
      host_policy: {
        builtin_allowed_hosts: ["pypi.org", "crates.io"],
      },
    });

    render(<IntakePanel />);

    const formatsBtn = screen.getByRole("button", { name: /Show supported formats/i });
    fireEvent.click(formatsBtn);

    expect(api.getIngestCapabilities).toHaveBeenCalled();

    await waitFor(() => {
      expect(screen.getByText("Accepted Source Formats & Shorthands")).toBeInTheDocument();
      expect(screen.getByText("pypi:requests@2.32.3")).toBeInTheDocument();
      expect(screen.getByText(".tar.gz")).toBeInTheDocument();
    });

    // Clicking an example should fill the input
    const exampleCard = screen.getByText("pypi:requests@2.32.3").closest("div");
    if (exampleCard) {
      fireEvent.click(exampleCard);
      const input = screen.getByRole("textbox", { name: /Universal source specification or URL/i });
      expect((input as HTMLInputElement).value).toBe("pypi:requests@2.32.3");
    }
  });
});
