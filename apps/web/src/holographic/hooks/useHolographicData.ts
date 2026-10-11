/**
 * Hook for fetching holographic reconstruction data from the backend API
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { VisualizationResponse, CausalGraph } from "../types";
import {
  fetchHolographicReconstruction,
  simulateCounterfactual,
  fetchAnomalies,
  fetchBoundaryLayers,
  apiResponseToCausalGraph,
  HolographicReconstructionParams,
  CounterfactualParams
} from "../api";

// Stable identity for the default params — a fresh {} per render would change
// `reconstruct`'s useCallback identity every render and make the autofetch
// effect refetch forever.
const EMPTY_RECONSTRUCTION_PARAMS: Partial<HolographicReconstructionParams> = {};

export interface UseHolographicDataOptions {
  incidentId: string;
  autoFetch?: boolean;
  reconstructionParams?: Partial<HolographicReconstructionParams>;
}

export interface UseHolographicDataReturn {
  data: VisualizationResponse | null;
  causalGraph: CausalGraph | null;
  /** True while a holographic reconstruction fetch is in flight. */
  isLoading: boolean;
  /** True while a counterfactual simulation is in flight. */
  isCounterfactualLoading: boolean;
  error: string | null;
  counterfactualError: string | null;
  reconstruct: (params?: Partial<HolographicReconstructionParams>) => Promise<void>;
  runCounterfactual: (params: Omit<CounterfactualParams, "incident_id">) => Promise<any>;
  refetchAnomalies: () => Promise<void>;
  refetchBoundaryLayers: () => Promise<void>;
}

export function useHolographicData(options: UseHolographicDataOptions): UseHolographicDataReturn {
  const { incidentId, autoFetch = true, reconstructionParams = EMPTY_RECONSTRUCTION_PARAMS } = options;

  const [data, setData] = useState<VisualizationResponse | null>(null);
  const [causalGraph, setCausalGraph] = useState<CausalGraph | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isCounterfactualLoading, setIsCounterfactualLoading] = useState(false);
  const [counterfactualError, setCounterfactualError] = useState<string | null>(null);

  // Abort the previous fetch and ignore its resolution: with rapid incident
  // switching the stale request used to land LAST and overwrite the fresh
  // incident's data.
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const reconstruct = useCallback(async (overrideParams?: Partial<HolographicReconstructionParams>) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setError(null);

    try {
      const params: HolographicReconstructionParams = {
        incident_id: incidentId,
        ...reconstructionParams,
        ...overrideParams,
      };

      const response = await fetchHolographicReconstruction(params, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      setData(response);
      setCausalGraph(apiResponseToCausalGraph(response));
    } catch (err) {
      if (controller.signal.aborted) return; // superseded by a newer call
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      console.error("Holographic reconstruction failed:", err);
    } finally {
      // Only the newest call owns the loading flag — an aborted older call
      // must not clear it while the fresh fetch is still in flight.
      if (abortRef.current === controller) {
        setIsLoading(false);
      }
    }
  }, [incidentId, reconstructionParams]);

  const runCounterfactual = useCallback(async (params: Omit<CounterfactualParams, "incident_id">) => {
    // Counterfactual gets its own loading/error pair. Sharing `isLoading`
    // with reconstruct meant a simulation resolving mid-fetch flipped the
    // fetch's spinner off early, and vice versa; its errors also surfaced
    // as reconstruction errors.
    setIsCounterfactualLoading(true);
    setCounterfactualError(null);

    try {
      const result = await simulateCounterfactual({ ...params, incident_id: incidentId });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setCounterfactualError(message);
      console.error("Counterfactual simulation failed:", err);
      throw err;
    } finally {
      setIsCounterfactualLoading(false);
    }
  }, [incidentId]);

  const refetchAnomalies = useCallback(async () => {
    try {
      const result = await fetchAnomalies({ incident_id: incidentId });
      setData(prev => prev ? { ...prev, anomalies: result.anomalies } : null);
    } catch (err) {
      console.error("Failed to fetch anomalies:", err);
    }
  }, [incidentId]);

  const refetchBoundaryLayers = useCallback(async () => {
    try {
      const result = await fetchBoundaryLayers({ incident_id: incidentId });
      setData(prev => prev ? { ...prev, boundary_layers: result.boundary_layers } : null);
    } catch (err) {
      console.error("Failed to fetch boundary layers:", err);
    }
  }, [incidentId]);

  useEffect(() => {
    if (autoFetch && incidentId) {
      reconstruct();
    }
  }, [autoFetch, incidentId, reconstruct]);

  return {
    data,
    causalGraph,
    isLoading,
    isCounterfactualLoading,
    error,
    counterfactualError,
    reconstruct,
    runCounterfactual,
    refetchAnomalies,
    refetchBoundaryLayers,
  };
}