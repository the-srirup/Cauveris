/**
 * Holographic Reconstruction API Client
 * Fetches visualization data from backend and converts to frontend types
 */

import { VisualizationResponse, CausalGraph, visualizationResponseToCausalGraph } from "./types";

// Next.js provides no `import.meta.env` (Vite-only) — use the same env chain as lib/api.ts.
// Default must include the /v1 segment: the backend serves /api/v1/holographic/*.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000/api/v1";

export interface HolographicReconstructionParams {
  incident_id: string;
  enable_counterfactual?: boolean;
  enable_anomalies?: boolean;
  enable_multiscale?: boolean;
  use_gpu?: boolean;
  gpu_decay_type?: string;
  gpu_normalization?: string;
  gpu_time_step_ns?: number;
  gpu_max_kernel_time_ns?: number;
}

export interface CounterfactualParams {
  incident_id: string;
  intervention_type: string;
  target_component: string;
  scale_factor?: number;
  use_gpu?: boolean;
  gpu_decay_type?: string;
  gpu_normalization?: string;
  gpu_time_step_ns?: number;
  gpu_max_kernel_time_ns?: number;
}

export interface AnomalyParams {
  incident_id: string;
  use_gpu?: boolean;
  gpu_decay_type?: string;
  gpu_normalization?: string;
  gpu_time_step_ns?: number;
  gpu_max_kernel_time_ns?: number;
}

export interface BoundaryLayerParams {
  incident_id: string;
  use_gpu?: boolean;
  gpu_decay_type?: string;
  gpu_normalization?: string;
  gpu_time_step_ns?: number;
  gpu_max_kernel_time_ns?: number;
}

/**
 * Request options shared by all fetchers (fetch-standard AbortSignal, so
 * hooks can cancel superseded requests instead of letting stale responses
 * overwrite a newer incident's data).
 */
export interface RequestOptions {
  signal?: AbortSignal;
}

/**
 * Fetch holographic reconstruction data
 */
export async function fetchHolographicReconstruction(
  params: HolographicReconstructionParams,
  options: RequestOptions = {}
): Promise<VisualizationResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set("incident_id", params.incident_id);
  if (params.enable_counterfactual !== undefined) searchParams.set("enable_counterfactual", String(params.enable_counterfactual));
  if (params.enable_anomalies !== undefined) searchParams.set("enable_anomalies", String(params.enable_anomalies));
  if (params.enable_multiscale !== undefined) searchParams.set("enable_multiscale", String(params.enable_multiscale));
  if (params.use_gpu !== undefined) searchParams.set("use_gpu", String(params.use_gpu));
  if (params.gpu_decay_type) searchParams.set("gpu_decay_type", params.gpu_decay_type);
  if (params.gpu_normalization) searchParams.set("gpu_normalization", params.gpu_normalization);
  if (params.gpu_time_step_ns) searchParams.set("gpu_time_step_ns", String(params.gpu_time_step_ns));
  if (params.gpu_max_kernel_time_ns) searchParams.set("gpu_max_kernel_time_ns", String(params.gpu_max_kernel_time_ns));

  const response = await fetch(`${API_BASE}/holographic/reconstruction?${searchParams.toString()}`, {
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Create holographic reconstruction with custom parameters (POST)
 */
export async function createHolographicReconstruction(
  params: HolographicReconstructionParams
): Promise<VisualizationResponse> {
  const response = await fetch(`${API_BASE}/holographic/reconstruction`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Run counterfactual simulation
 */
export async function simulateCounterfactual(
  params: CounterfactualParams,
  options: RequestOptions = {}
): Promise<any> {
  const searchParams = new URLSearchParams();
  searchParams.set("incident_id", params.incident_id);
  searchParams.set("intervention_type", params.intervention_type);
  searchParams.set("target_component", params.target_component);
  if (params.scale_factor !== undefined) searchParams.set("scale_factor", String(params.scale_factor));
  if (params.use_gpu !== undefined) searchParams.set("use_gpu", String(params.use_gpu));
  if (params.gpu_decay_type) searchParams.set("gpu_decay_type", params.gpu_decay_type);
  if (params.gpu_normalization) searchParams.set("gpu_normalization", params.gpu_normalization);
  if (params.gpu_time_step_ns) searchParams.set("gpu_time_step_ns", String(params.gpu_time_step_ns));
  if (params.gpu_max_kernel_time_ns) searchParams.set("gpu_max_kernel_time_ns", String(params.gpu_max_kernel_time_ns));

  const response = await fetch(`${API_BASE}/holographic/counterfactual?${searchParams.toString()}`, {
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Get detected anomalies
 */
export async function fetchAnomalies(
  params: AnomalyParams,
  options: RequestOptions = {}
): Promise<{ anomalies: any[] }> {
  const searchParams = new URLSearchParams();
  searchParams.set("incident_id", params.incident_id);
  if (params.use_gpu !== undefined) searchParams.set("use_gpu", String(params.use_gpu));
  if (params.gpu_decay_type) searchParams.set("gpu_decay_type", params.gpu_decay_type);
  if (params.gpu_normalization) searchParams.set("gpu_normalization", params.gpu_normalization);
  if (params.gpu_time_step_ns) searchParams.set("gpu_time_step_ns", String(params.gpu_time_step_ns));
  if (params.gpu_max_kernel_time_ns) searchParams.set("gpu_max_kernel_time_ns", String(params.gpu_max_kernel_time_ns));

  const response = await fetch(`${API_BASE}/holographic/anomalies?${searchParams.toString()}`, {
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Get boundary layer data
 */
export async function fetchBoundaryLayers(
  params: BoundaryLayerParams,
  options: RequestOptions = {}
): Promise<{ boundary_layers: any }> {
  const searchParams = new URLSearchParams();
  if (params.use_gpu !== undefined) searchParams.set("use_gpu", String(params.use_gpu));
  if (params.gpu_decay_type) searchParams.set("gpu_decay_type", params.gpu_decay_type);
  if (params.gpu_normalization) searchParams.set("gpu_normalization", params.gpu_normalization);
  if (params.gpu_time_step_ns) searchParams.set("gpu_time_step_ns", String(params.gpu_time_step_ns));
  if (params.gpu_max_kernel_time_ns) searchParams.set("gpu_max_kernel_time_ns", String(params.gpu_max_kernel_time_ns));

  const response = await fetch(`${API_BASE}/holographic/boundary-layers/${params.incident_id}?${searchParams.toString()}`, {
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

/**
 * Convert API response to causal graph for legacy hook compatibility
 */
export function apiResponseToCausalGraph(response: VisualizationResponse): CausalGraph {
  return visualizationResponseToCausalGraph(response);
}

/**
 * Default reconstruction parameters
 */
export interface ComparisonParams {
  incident_id_a: string;
  incident_id_b: string;
  include_visualization?: boolean;
}

export interface NodeComparison {
  node_id: string;
  in_a: boolean;
  in_b: boolean;
  cpu_delta: number;
  memory_delta: number;
  error_rate_delta: number;
  latency_delta: number;
  health_delta: number;
  metrics_a: Record<string, number>;
  metrics_b: Record<string, number>;
}

export interface IncidentComparisonResponse {
  incident_a: string;
  incident_b: string;
  timestamp_ns: number;
  node_comparisons: NodeComparison[];
  summary: Record<string, any>;
}

/**
 * Compare two incidents
 */
export async function compareIncidents(
  params: ComparisonParams,
  options: RequestOptions = {}
): Promise<IncidentComparisonResponse> {
  const response = await fetch(`${API_BASE}/holographic/comparison`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal: options.signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

export const defaultReconstructionParams: Partial<HolographicReconstructionParams> = {
  enable_counterfactual: false,
  enable_anomalies: true,
  enable_multiscale: true,
  use_gpu: true,
  gpu_decay_type: "exponential",
  gpu_normalization: "l1",
  gpu_time_step_ns: 1000000,
  gpu_max_kernel_time_ns: 10000000000,
};