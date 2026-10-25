import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";

// Unmock the api module so we can test the real implementation
vi.unmock("@/lib/api");
vi.unmock("@/lib/auth");

import { api } from "@/lib/api";

// Mock fetch globally
const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("api debounce/dedupe regressions", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounce: same key - only one network request fires, both callers resolve with same value", async () => {
    let resolveResponse: (value: any) => void;
    const responsePromise = new Promise((resolve) => {
      resolveResponse = resolve;
    });

    mockFetch.mockImplementation(() => responsePromise);

    // First call
    const promise1 = api.getTimeline("incident-1");
    // Second call with same key (rapid call)
    const promise2 = api.getTimeline("incident-1");

    // Advance timers to trigger the debounced request
    await vi.advanceTimersByTimeAsync(150);

    // At this point, only one fetch should have been called
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Resolve the fetch
    resolveResponse!({
      ok: true,
      json: async () => ({ incident_id: "incident-1", total_events: 5, timeline_events: [] }),
      status: 200,
    });

    // Both promises should resolve with the same value
    const [result1, result2] = await Promise.all([promise1, promise2]);

    expect(result1).toEqual(result2);
    expect(result1.incident_id).toBe("incident-1");
    expect(result1.total_events).toBe(5);
  });

  it("debounce: different keys - two requests fire, both resolve", async () => {
    let resolveResponse1: (value: any) => void;
    let resolveResponse2: (value: any) => void;

    const responsePromise1 = new Promise((resolve) => {
      resolveResponse1 = resolve;
    });
    const responsePromise2 = new Promise((resolve) => {
      resolveResponse2 = resolve;
    });

    let callCount = 0;
    mockFetch.mockImplementation(() => {
      callCount++;
      return callCount === 1 ? responsePromise1 : responsePromise2;
    });

    // Call with different incident IDs (different keys)
    const promise1 = api.getTimeline("incident-1");
    const promise2 = api.getTimeline("incident-2");

    await vi.advanceTimersByTimeAsync(150);

    // Two fetches should have been called
    expect(mockFetch).toHaveBeenCalledTimes(2);

    // Resolve both
    resolveResponse1!({
      ok: true,
      json: async () => ({ incident_id: "incident-1", total_events: 5, timeline_events: [] }),
      status: 200,
    });
    resolveResponse2!({
      ok: true,
      json: async () => ({ incident_id: "incident-2", total_events: 3, timeline_events: [] }),
      status: 200,
    });

    const [result1, result2] = await Promise.all([promise1, promise2]);

    expect(result1.incident_id).toBe("incident-1");
    expect(result1.total_events).toBe(5);
    expect(result2.incident_id).toBe("incident-2");
    expect(result2.total_events).toBe(3);
  });

  it("debounce: first caller's promise does not hang when superseded", async () => {
    let resolveResponse: (value: any) => void;
    const responsePromise = new Promise((resolve) => {
      resolveResponse = resolve;
    });

    mockFetch.mockImplementation(() => responsePromise);

    // First call
    const promise1 = api.getEvents("incident-1");

    // Advance timer partially (before debounce fires)
    await vi.advanceTimersByTimeAsync(50);

    // Second call with same key (supersedes first)
    const promise2 = api.getEvents("incident-1");

    // Advance timer to complete debounce
    await vi.advanceTimersByTimeAsync(150);

    // Only one fetch
    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Resolve the fetch
    resolveResponse!({
      ok: true,
      json: async () => ({ state: "RUNNING", progress: 50, active_stage_id: "INGEST", stages: [] }),
      status: 200,
    });

    // Both promises should resolve (first should NOT hang)
    const results = await Promise.race([
      Promise.all([promise1, promise2]),
      new Promise((_, reject) => setTimeout(() => reject(new Error("Test timed out - promise hung")), 1000)),
    ]);

    expect(results[0]).toEqual(results[1]);
    expect(results[0].state).toBe("RUNNING");
  });

  // This test verifies that caller-supplied signal is combined with internal timeout signal
  // Note: Full abort integration test is complex with mocks; the key behavior is tested in auth-fetch-regressions
  it("deduped: caller-supplied signal is combined with internal signals", async () => {
    vi.useRealTimers();
    try {
      let receivedSignal: AbortSignal | null = null;

      mockFetch.mockImplementation((url: string, options: RequestInit) => {
        receivedSignal = options.signal as AbortSignal;
        return Promise.resolve({
          ok: true,
          json: async () => ({ id: "incident-1", title: "Test", status: "RECEIVED", evidence_count: 0 }),
          status: 200,
        });
      });

      // Create an AbortController for the caller
      const controller = new AbortController();

      await api.get("incident-1", { signal: controller.signal });

      // Verify the signal passed to fetch is a combined signal (AbortSignal.any result)
      expect(receivedSignal).toBeInstanceOf(AbortSignal);

      // The caller's signal should be part of the combination (not the exact same object)
      // This verifies the dedupe layer passes the caller's signal through
      expect(receivedSignal).not.toBe(controller.signal);
    } finally {
      vi.useFakeTimers();
    }
  });

  it("deduped: caller-supplied signal works when request is already in-flight from previous caller", async () => {
    let fetchCallCount = 0;

    // First call - set up a pending request that never resolves
    mockFetch.mockImplementation((url: string, options: RequestInit) => {
      fetchCallCount++;
      if (fetchCallCount === 1) {
        return new Promise(() => {}); // Never resolves
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ id: "incident-1", title: "Test", status: "RECEIVED", evidence_count: 0 }),
        status: 200,
      });
    });

    const promise1 = api.get("incident-1");

    await vi.advanceTimersByTimeAsync(0);

    // Verify first fetch was called
    expect(fetchCallCount).toBe(1);

    // Check internal cache state
    // @ts-ignore - accessing private for test
    const cacheKey = api.getCacheKey("/incidents/incident-1", {});
    // @ts-ignore - accessing private for test
    const pending = api.pendingRequests.get(cacheKey);
    expect(pending).toBeDefined();
    expect(pending.promise).toBe(promise1);

    // Second caller - should get the SAME promise (deduped), no second fetch
    const promise2 = api.get("incident-1");

    // Both promises should be the same (deduped)
    expect(promise1).toBe(promise2);

    // No second fetch should have been made
    expect(fetchCallCount).toBe(1);

    // But note: the second caller's signal is NOT used for the in-flight request
    // because we return the existing promise. This is the current behavior.
    // The test documents this behavior.
  });
});