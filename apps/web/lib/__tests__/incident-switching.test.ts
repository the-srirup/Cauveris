import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useActiveIncident } from "../useIncident";
import { api } from "../api";

describe("useActiveIncident Incident Switching State Isolation", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("clears stale incident state immediately when switching incident IDs", async () => {
    vi.spyOn(api, "get").mockImplementation(async (id: string) => {
      return {
        id,
        title: `Incident ${id}`,
        status: "OBSERVED",
        evidence_count: 5,
      };
    });

    const { result } = renderHook(() => useActiveIncident());

    // 1. Initial state is null
    expect(result.current.incidentId).toBeNull();
    expect(result.current.incident).toBeNull();

    // 2. Load Incident A
    await act(async () => {
      await result.current.loadIncident("INC-AAA");
    });
    expect(result.current.incidentId).toBe("INC-AAA");
    expect(result.current.incident?.id).toBe("INC-AAA");
    expect(result.current.incident?.title).toBe("Incident INC-AAA");

    // 3. Switch to Incident B via setIncidentId: stale incident A state MUST be cleared immediately
    act(() => {
      result.current.setIncidentId("INC-BBB");
    });

    expect(result.current.incidentId).toBe("INC-BBB");
    // Crucial invariant: stale incident data from INC-AAA must be cleared
    expect(result.current.incident).toBeNull();

    // 4. Loading Incident B populates Incident B data
    await act(async () => {
      await result.current.loadIncident("INC-BBB");
    });
    expect(result.current.incidentId).toBe("INC-BBB");
    expect(result.current.incident?.id).toBe("INC-BBB");
    expect(result.current.incident?.title).toBe("Incident INC-BBB");

    // 5. Switching to null clears both ID and data
    act(() => {
      result.current.setIncidentId(null);
    });
    expect(result.current.incidentId).toBeNull();
    expect(result.current.incident).toBeNull();
  });
});
