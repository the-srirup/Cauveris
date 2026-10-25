/**
 * API Client for Cauveris Backend
 * Handles all communication with the FastAPI backend
 */

import {
  CauverisError,
  networkError,
  timeoutError,
  apiError,
  incidentNotFound,
  pipelineFailed,
  evidenceUploadFailed,
  secretsDetected,
  patchApplyFailed,
  patchVerificationFailed,
  modelUnavailable,
  clientStorageError,
  configMissing,
  unknownError,
  handleApiError,
  retryWithBackoff,
  ErrorCodes,
} from "./errors";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000/api/v1";

export type IncidentStatus = "RECEIVED" | "VALIDATED" | "REJECTED" | "PROCESSING" | "COMPLETED" | "FAILED" | "IDLE" | "RUNNING" | "SUCCESS" | "DEGRADED" | "CANCELLED" | string;

export type StageStatus = "PENDING" | "RUNNING" | "SUCCESS" | "DEGRADED" | "FAILED" | "SKIPPED" | "CANCELLED";

// Re-export error types and functions for consumers
export {
  CauverisError,
  networkError,
  timeoutError,
  apiError,
  incidentNotFound,
  pipelineFailed,
  evidenceUploadFailed,
  secretsDetected,
  patchApplyFailed,
  patchVerificationFailed,
  modelUnavailable,
  clientStorageError,
  configMissing,
  unknownError,
  handleApiError,
  retryWithBackoff,
  ErrorCodes,
};

import { authenticatedFetch, useAuthStore, FetchRequestInit } from './auth';

export interface PipelineStageInfo {
  id: string;
  name: string;
  description: string;
  required: boolean;
  depends_on: string[];
  status: StageStatus;
  error?: string | null;
  details?: Record<string, any>;
  duration_ms?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface PipelineEventsResponse {
  state: "IDLE" | "PENDING" | "RUNNING" | "SUCCESS" | "DEGRADED" | "FAILED" | "CANCELLED" | string;
  progress: number;
  active_stage_id?: string | null;
  stages?: PipelineStageInfo[];
  error?: string | null;
  is_demonstration?: boolean;
  started_at?: string | null;
  completed_at?: string | null;
  timestamp?: string;
}

export interface EvidenceValidationSummary {
  incident_id: string;
  validation_status: "completed" | "PASSED" | "WARNING" | "FAILED" | string;
  status?: "PASSED" | "WARNING" | "FAILED" | string;
  summary_status?: "PASSED" | "WARNING" | "FAILED" | string;
  is_valid: boolean;
  evidence_count: number;
  required_evidence_count: number;
  missing_required_evidence: string[];
  secrets_detected_count: number;
  checksums_valid: boolean;
  schema_valid: boolean;
  is_demonstration?: boolean;
  evidence_items?: EvidenceItem[];
}

export interface SystemHealthResponse {
  status: string;
  service: string;
  version: string;
  timestamp?: string;
  latency_ms?: number;
}

export interface ModelProviderHealthResponse {
  status: string;
  provider: string;
  mode: string;
  cloud_credentials_required: boolean;
  nebius_configured?: boolean;
  timestamp?: string;
}

export interface StatusCenterResponse {
  status: string;
  incidents_count: number;
  active_incident_id: string | null;
  current_stage: string;
  model_route: string;
  processing_mode?: string;
  backend_health?: SystemHealthResponse;
  model_provider?: ModelProviderHealthResponse;
  sandbox_status: string;
  timestamp?: string;
}

export interface Incident {
  id: string;
  title: string;
  status: IncidentStatus;
  pipeline_state?: string;
  evidence_count: number;
  required_evidence_count?: number;
  missing_required_evidence?: string[];
  description?: string;
  system_name?: string;
  approximate_time?: string;
  manifest?: Record<string, any>;
  timeline_events?: TimelineEvent[];
  timeline_events_count?: number;
  evidence_items?: EvidenceItem[];
  is_demonstration?: boolean;
}

export interface EvidenceItem {
  file_path: string;
  file_type: string;
  size_bytes: number;
  checksum_sha256: string;
  status: string;
  is_required: boolean;
  validation_errors?: string[];
}

export interface TimelineEvent {
  timestamp_ns: number;
  original_timestamp?: string;
  original_timestamp_s?: number;
  event_type?: string;
  source_type?: string;
  lane?: string;
  source?: string;
  message?: string;
  attributes?: Record<string, any>;
  confidence?: number;
  status?: string;
  relative_timestamp_s?: number;
  relative_timestamp_ns?: number;
  temporal_trust?: number;
  event_id?: string;
  supporting_artifact_ids?: string[];
  contradicting_artifact_ids?: string[];
}

export interface IncidentTimeline {
  incident_id: string;
  total_events: number;
  timeline_events: TimelineEvent[];
  clock_alignment?: any;
}

export interface TemporalAnalysis {
  incident_id: string;
  violations?: any[];
  clock_alignment?: any;
  temporal_analysis?: any;
  anomalies?: any[];
  confidence_score?: number;
  is_time_anomalous?: boolean;
}

export interface Hypothesis {
  id: string;
  hypothesis_id?: string;
  title: string;
  description: string;
  causal_claim?: string;
  confidence: number;
  confidence_prior?: number;
  status: string;
  intervention?: string;
  evidence_count?: number;
  supporting_artifact_ids?: string[];
  contradicting_artifact_ids?: string[];
  missing_evidence?: string[];
  reproduction_rate?: number;
  test_result?: string;
}

export interface TrajectoryPoint {
  t: number;
  x: number;
  y: number;
  v?: number;
  heading?: number;
  latency_ms: number;
  status: string;
  is_stale: boolean;
  emergency_stop: boolean;
  batch_wait_ms?: number;
  gpu_compute_ms?: number;
  network_delay_ms?: number;
}

/**
 * One digital-twin trial run: the full 2D path the robot actually traced
 * under that trial's fault configuration, plus the twin's own verdict.
 */
export interface TrialRun {
  path: TrajectoryPoint[];
  final_status: string;
  is_confirmed_safe: boolean;
  stop_coordinate?: { x: number; y: number } | null;
  halt_reason?: string | null;
  distance_traveled_m: number;
}

export interface Experiment {
  id: string;
  experiment_id?: string;
  name: string;
  hypothesis_id?: string;
  branch_name?: string;
  status: string;
  intervention?: string;
  reproduction_rate?: number;
  result?: boolean;
  failure_oracle?: any;
  metrics?: Record<string, any>;
  trajectory?: TrajectoryPoint[];
  trajectories?: any[];
  trial_count?: number;
  reproduction_count?: number;
  conclusion?: string;
  logs_artifact_id?: string;
  metrics_artifact_id?: string;
  replay_artifact_id?: string;
}

/**
 * The calibrated incident model.
 *
 * `model_status` is the honest answer to "can this model predict?":
 * `fitted` means the parameters were fitted to this incident's measurements,
 * `declared-configuration-only` means the bundle declared values that were
 * never corroborated by a measurement, and `uncalibrated` means there was
 * nothing to calibrate against.
 */
export interface IncidentSystemModel {
  incident_id: string;
  bundle_root?: string | null;
  model_status: "fitted" | "declared-configuration-only" | "uncalibrated";
  parameters: Record<string, number>;
  parameter_sources: Record<string, string>;
  parameters_from_evidence: Record<string, boolean>;
  budget: {
    freshness_budget_ms: number;
    control_deadline_ms: number;
    required_rate_hz: number;
    emergency_stop_on_stale: boolean;
    sources: Record<string, string>;
  };
  kinematics: {
    max_speed_mps: number;
    nominal_speed_mps: number;
    acceleration_mps2: number;
    braking_deceleration_mps2: number;
    reaction_time_s: number;
    safety_margin_m: number;
    sample_count: number;
    source: string;
  };
  calibration?: {
    params: Record<string, number>;
    score: number;
    quality: string;
    targets: Record<string, number | null>;
    residuals: Record<string, number | null>;
    fitted: Record<string, number | null>;
    compared: Record<string, number | null>;
    age_measurement_basis: string;
    worst_target?: string | null;
    worst_relative_error?: number | null;
    notes: string[];
  } | null;
  latency_distribution: Record<string, number>;
  baseline_distribution: Record<string, number>;
  incident_distribution: Record<string, number>;
  transport_distribution: Record<string, number>;
  clock_skew_ms: number;
  observation_window_s: number;
  simulation_horizon_s: number;
  change_point_time?: string | null;
  change_point_evidence: string[];
  config_deltas: Array<{
    key: string;
    role: string;
    old_value: any;
    new_value: any;
    source: string;
    description: string;
    file: string;
    deployment_id: string;
    deployment_time?: string | null;
  }>;
  notes: string[];
  consistency_findings: Array<Record<string, any>>;
}

export interface PatchCandidate {
  id: string;
  candidate_id?: string;
  title: string;
  diff?: string;
  score: number;
  verified: boolean;
  test_result?: string;
  unified_diff?: string;
  affected_files?: string[];
  lines_changed?: number;
  rationale?: string;
  applied_cleanly?: boolean;
  regression_test_passes_after?: boolean;
  original_failure_not_reproduced?: boolean;
  existing_tests_pass?: boolean;
  safety_invariants_pass?: boolean;
  performance_within_budget?: boolean;
  forbidden_change_scan_passes?: boolean;
  rollback_test_passes?: boolean;
}

export interface VerificationReport {
  passed: boolean;
  message: string;
  details?: any;
  patch_candidate_id?: string;
  applies_cleanly?: boolean;
  regression_test_fails_before?: boolean;
  regression_test_passes_after?: boolean;
  original_failure_not_reproduced?: boolean;
  existing_tests_pass?: boolean;
  safety_invariants_pass?: boolean;
  performance_within_budget?: boolean;
  forbidden_change_scan_passes?: boolean;
  rollback_test_passes?: boolean;
  verified?: boolean;
}

export interface ApplyPatchResult {
  success: boolean;
  message?: string;
  details?: string;
  applied?: boolean;
  dry_run?: boolean;
  status?: string;
}

export interface IncidentReport {
  incident_id: string;
  title?: string;
  description?: string;
  system_name?: string;
  approximate_time?: string;
  evidence_summary?: {
    total_evidence_items: number;
    required_evidence_items: number;
    missing_required_evidence: string[];
  };
  timeline?: TimelineEvent[];
  temporal_analysis?: any;
  hypotheses?: Hypothesis[];
  experiments?: Experiment[];
  patch_candidates?: PatchCandidate[];
  verification_reports?: VerificationReport[];
  status?: string;
  patch_package_path?: string;
  [key: string]: any;
}

/** One side of the before/after twin comparison, as measured by the backend. */
export interface ReplaySide {
  trial_count: number;
  reproduction_count: number;
  reproduction_rate: number;
  avg_latency_ms: number;
  p99_latency_ms: number;
  max_latency_ms: number;
  avg_batch_wait_ms?: number | null;
  avg_gpu_compute_ms?: number | null;
  avg_network_delay_ms?: number | null;
  goal_reached_count: number;
  emergency_stop_count: number;
  is_confirmed_safe: boolean;
  halt_reason?: string | null;
  stop_coordinate?: { x: number; y: number } | null;
  trajectory: TrajectoryPoint[];
  trajectories: TrialRun[];
  parameters: Record<string, any>;
}

export interface VictoryReplayResponse {
  incident_id: string;
  available: boolean;
  reason?: string;
  experiment?: {
    experiment_id: string;
    hypothesis_id: string;
    branch_name: string;
    intervention: string;
    conclusion?: string | null;
    reproduction_rate?: number | null;
  };
  applied_configuration?: Record<string, string>;
  before: ReplaySide | null;
  after: ReplaySide | null;
  delta: Record<string, number | null> | null;
  verdict?: {
    failure_eliminated: boolean;
    regression_introduced: boolean;
    improvement: boolean;
  };
  freshness_budget_ms?: number;
  patch?: (PatchCandidate & { id?: string; diff?: string }) | null;
  verification?: VerificationReport | null;
}

export interface TemporalVisualizationEvent {
  id: string;
  ts: number;
  domain: string;
  label: string;
  merge_group?: string | null;
  confidence: number;
  lane: string;
  source: string;
  source_type: string;
  message: string;
  clock_domain: string;
  attributes: Record<string, any>;
}

export interface TemporalVisualizationConnection {
  source: string;
  target: string;
  type: "causal_edge" | "violation" | "loop_edge";
  provenance?: string;
  confidence?: number;
  description?: string;
  loop_id?: string | null;
}

export interface TemporalVisualizationCausalStep {
  source: string;
  target: string;
  provenance: string;
  source_lane: string;
  target_lane: string;
  source_message: string;
  target_message: string;
}

export interface TemporalVisualizationCausalChain {
  terminal_id: string;
  terminal_lane: string;
  terminal_message: string;
  terminal_source: string;
  terminal_domain: string;
  is_safety_outcome: boolean;
  length: number;
  steps: TemporalVisualizationCausalStep[];
}

export interface TemporalVisualizationLane {
  lane: string;
  tier: number;
  event_count: number;
  domains: string[];
  sources: string[];
  start_s: number;
  end_s: number;
  first_message: string;
  last_message: string;
}

export interface TemporalVisualizationLaneEdge {
  source: string;
  target: string;
  edge_count: number;
  provenance: Record<string, number>;
}

export interface TemporalVisualizationResponse {
  events?: TemporalVisualizationEvent[];
  connections?: TemporalVisualizationConnection[];
  anomaly_points?: Array<{
    id: string;
    type: string;
    severity: number;
    confidence: number;
    explanation: string;
  }>;
  untrusted_bands?: Array<{
    start_s: number;
    end_s: number;
    reason: string;
    description: string;
  }>;
  causal_chains?: TemporalVisualizationCausalChain[];
  lanes?: TemporalVisualizationLane[];
  lane_edges?: TemporalVisualizationLaneEdge[];
  summary?: {
    total_events: number;
    connections: number;
    anomaly_count: number;
    time_loop_count: number;
    is_anomalous: boolean;
    confidence: number;
    causal_edge_count: number;
    violation_count: number;
    provenance_breakdown: Record<string, number>;
    chain_count: number;
    lane_count: number;
  };
  bulk_nodes?: Array<{
    id: string;
    name?: string;
    type?: string;
    health?: number;
    confidence?: number;
    metrics?: Record<string, any>;
    config_changed?: boolean;
    position?: number[];
    size?: number;
    color?: string;
    [key: string]: any;
  }>;
  bulk_edges?: Array<{
    source: string;
    target: string;
    type?: string;
    thickness?: number;
    latency_ms?: number;
    source_health?: number;
    target_health?: number;
    color?: string;
    [key: string]: any;
  }>;
}

export interface HolographicData {
  incident_id: string;
  bulk_nodes: Array<{
    id: string;
    name: string;
    type: string;
    position: [number, number, number];
    size: number;
    color: string;
    health: number;
    metrics: {
      cpu_usage: number;
      memory_usage: number;
      network_usage: number;
      error_rate: number;
      latency_p99_ms: number;
    };
    confidence: number;
    config_changed: boolean;
  }>;
  bulk_edges: Array<{
    source: string;
    target: string;
    type: "causal" | "network";
    thickness: number;
    color: string;
    latency_ms: number;
    source_health: number;
    target_health: number;
    loss_rate?: number;
    bandwidth_mbps?: number;
  }>;
  boundary_layers: Record<string, Record<string, any>>;
  scale_hierarchy: any[];
  ambiguity_regions: Array<{
    component: string;
    dimension: string;
    affected_dimensions: string[];
    time_range_ns: [number, number];
    duration_ms: number;
    ambiguity_score: number;
    missing_layers: string[];
    description: string;
    severity: "low" | "medium" | "high";
  }>;
  counterfactual: any;
  anomalies: any[];
  metadata: Record<string, any>;
}

// Request deduplication cache
interface PendingRequest<T> {
  promise: Promise<T>;
  abortController: AbortController;
  timestamp: number;
}

// For debounced requests: track pending resolvers per cache key
interface DebounceState {
  timer: NodeJS.Timeout;
  resolvers: Array<(value: any) => void>;
  rejectors: Array<(reason: any) => void>;
}

// API Client
class ApiClient {
  private baseUrl: string;
  private pendingRequests: Map<string, PendingRequest<any>> = new Map();
  private debounceTimers: Map<string, DebounceState> = new Map();
  private readonly REQUEST_CACHE_TTL = 5000; // 5 seconds
  private readonly DEBOUNCE_MS = 150; // 150ms debounce for repeated calls

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private getCacheKey(endpoint: string, options: FetchRequestInit = {}): string {
    const method = options.method || "GET";
    const body = options.body ? JSON.stringify(options.body) : "";
    return `${method}:${endpoint}:${body}`;
  }

  private cleanupCache(): void {
    const now = Date.now();
    for (const [key, value] of this.pendingRequests.entries()) {
      if (now - value.timestamp > this.REQUEST_CACHE_TTL) {
        this.pendingRequests.delete(key);
      }
    }
  }

  private async request<T>(endpoint: string, options: FetchRequestInit = {}): Promise<T> {
    // Use authenticated fetch which handles token refresh automatically
    try {
      return await authenticatedFetch<T>(endpoint, options);
    } catch (err: any) {
      if (err instanceof CauverisError) {
        throw err;
      }
      // Convert generic errors to CauverisError
      if (err.name === 'AbortError' || err.message?.includes('timeout')) {
        throw timeoutError(endpoint, 15000);
      }
      if (err.message?.includes('Failed to fetch') || err.message?.includes('Cannot connect')) {
        throw networkError(`Cannot connect to Cauveris API at ${this.baseUrl}. Please verify the backend is running.`);
      }
      throw unknownError(err.message || "Unknown API error", err, { endpoint });
    }
  }

  // Deduplicated request - returns cached promise if identical request is in-flight
  requestDeduped<T>(endpoint: string, options: FetchRequestInit = {}): Promise<T> {
    this.cleanupCache();

    // Only deduplicate GET requests
    const method = options.method || "GET";
    if (method !== "GET") {
      return this.request<T>(endpoint, options);
    }

    const cacheKey = this.getCacheKey(endpoint, options);
    const existing = this.pendingRequests.get(cacheKey);

    if (existing) {
      // Return existing promise (callers share the same in-flight request)
      return existing.promise as Promise<T>;
    }

    // Create new request
    const abortController = new AbortController();

    // If caller provided a signal, link it to our internal controller
    // so either can abort the request
    if (options.signal) {
      const callerSignal = options.signal;
      if (callerSignal.aborted) {
        abortController.abort();
      } else {
        callerSignal.addEventListener("abort", () => abortController.abort(), { once: true });
      }
    }

    const promise = this.request<T>(endpoint, {
      ...options,
      signal: abortController.signal,
    }).finally(() => {
      // Clean up after completion
      this.pendingRequests.delete(cacheKey);
    });

    this.pendingRequests.set(cacheKey, {
      promise,
      abortController,
      timestamp: Date.now(),
    });

    return promise;
  }

  // Debounced request - delays execution and deduplicates rapid calls
  async requestDebounced<T>(endpoint: string, options: FetchRequestInit = {}, debounceMs: number = this.DEBOUNCE_MS): Promise<T> {
    const cacheKey = this.getCacheKey(endpoint, options);

    return new Promise<T>((resolve, reject) => {
      // Get or create debounce state for this key
      let state = this.debounceTimers.get(cacheKey);
      if (!state) {
        state = { timer: null as unknown as NodeJS.Timeout, resolvers: [], rejectors: [] };
        this.debounceTimers.set(cacheKey, state);
      }

      // Add this caller's resolve/reject to the list
      state.resolvers.push(resolve);
      state.rejectors.push(reject);

      // Clear existing debounce timer
      if (state.timer) {
        clearTimeout(state.timer);
      }

      // Set new timer
      state.timer = setTimeout(() => {
        this.debounceTimers.delete(cacheKey);
        // Execute the request once, then resolve/reject ALL pending callers
        this.requestDeduped<T>(endpoint, options).then(
          (value) => {
            for (const r of state.resolvers) r(value);
          },
          (reason) => {
            for (const r of state.rejectors) r(reason);
          }
        );
      }, debounceMs);
    });
  }

  // Cancel a specific request by cache key
  cancelRequest(endpoint: string, options: FetchRequestInit = {}): void {
    const cacheKey = this.getCacheKey(endpoint, options);
    const existing = this.pendingRequests.get(cacheKey);
    if (existing) {
      existing.abortController.abort();
      this.pendingRequests.delete(cacheKey);
    }
  }

  // Cancel all pending requests
  cancelAllRequests(): void {
    for (const [, value] of this.pendingRequests.entries()) {
      value.abortController.abort();
    }
    this.pendingRequests.clear();

    for (const [, state] of this.debounceTimers.entries()) {
      if (state.timer) {
        clearTimeout(state.timer);
      }
      // Reject all pending debounced callers
      for (const reject of state.rejectors) {
        reject(new DOMException("Cancelled", "AbortError"));
      }
    }
    this.debounceTimers.clear();
  }

  // Health check
  async health(): Promise<SystemHealthResponse> {
    return this.request<SystemHealthResponse>("/health");
  }

  // Model provider health
  async modelHealth(): Promise<ModelProviderHealthResponse> {
    return this.request<ModelProviderHealthResponse>("/model-health");
  }

  // Incident operations
  list(): Promise<{ incidents: Incident[]; count?: number }> {
    return this.requestDeduped<{ incidents: Incident[]; count?: number }>("/incidents");
  }

  get(incidentId: string): Promise<Incident> {
    return this.requestDeduped<Incident>(`/incidents/${incidentId}`);
  }

  async create(golden: boolean = false, data?: { title?: string; description?: string; system_name?: string; custom_id?: string }): Promise<{ incident_id: string; message: string; is_demonstration?: boolean }> {
    const url = `/incidents?golden=${golden}`;
    if (data) {
      return this.request<{ incident_id: string; message: string; is_demonstration?: boolean }>(url, {
        method: "POST",
        body: JSON.stringify(data),
      });
    }
    return this.request<{ incident_id: string; message: string; is_demonstration?: boolean }>(url, {
      method: "POST",
    });
  }

  // Cancel investigation
  async cancel(incidentId: string): Promise<{ message: string; incident_id: string; state: string }> {
    return this.request<{ message: string; incident_id: string; state: string }>(`/incidents/${incidentId}/cancel`, {
      method: "POST",
    });
  }

  // Reset investigation
  async reset(incidentId: string): Promise<{ message: string; incident_id: string; state: string; is_demonstration?: boolean; pipeline_summary?: any }> {
    return this.request<{ message: string; incident_id: string; state: string; is_demonstration?: boolean; pipeline_summary?: any }>(`/incidents/${incidentId}/reset`, {
      method: "POST",
    });
  }

  // Reset demo
  async resetDemo(): Promise<{ message: string; incident_id: string; state: string; is_demonstration?: boolean; pipeline_summary?: any }> {
    return this.request<{ message: string; incident_id: string; state: string; is_demonstration?: boolean; pipeline_summary?: any }>("/reset-demo", {
      method: "POST",
    });
  }

  // Upload incident file
  async uploadFile(incidentId: string, file: File): Promise<{ message: string; filename: string; size: number; evidence_count: number }> {
    const formData = new FormData();
    formData.append('file', file);

    const { accessToken } = useAuthStore.getState();
    const headers: Record<string, string> = {};
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    const response = await fetch(`${this.baseUrl}/incidents/${incidentId}/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail.map((d: any) => (d && typeof d === 'object' ? d.msg || d.message : String(d))).join(', ');
        } else if (errorData.detail && typeof errorData.detail === 'object') {
          errorMessage = errorData.detail.msg || errorData.detail.message || JSON.stringify(errorData.detail);
        } else if (typeof errorData.error === 'string') {
          errorMessage = errorData.error;
        }
      } catch {
        // Ignore json parse errors
      }
      throw new Error(errorMessage);
    }

    return response.json();
  }

  // Timeline operations - debounced for polling scenarios
  async getTimeline(incidentId: string): Promise<IncidentTimeline> {
    return this.requestDebounced<IncidentTimeline>(`/incidents/${incidentId}/timeline`);
  }

  // Temporal analysis
  getTemporalAnalysis(incidentId: string): Promise<TemporalAnalysis> {
    return this.requestDeduped<TemporalAnalysis>(`/incidents/${incidentId}/temporal-analysis`);
  }

  // Validation - POST, not deduplicated
  async validate(incidentId: string): Promise<EvidenceValidationSummary> {
    return this.request<EvidenceValidationSummary>(`/incidents/${incidentId}/validate`, { method: "POST" });
  }

  // Status checking - debounced for polling
  async getEvents(incidentId: string): Promise<PipelineEventsResponse> {
    return this.requestDebounced<PipelineEventsResponse>(`/incidents/${incidentId}/events`);
  }

  // Orchestration status center endpoint - debounced for polling
  async getStatusCenter(): Promise<StatusCenterResponse> {
    return this.requestDebounced<StatusCenterResponse>("/status-center");
  }

  // Get incident hypotheses
  getHypotheses(incidentId: string) {
    return this.requestDeduped<{ incident_id: string; count: number; hypotheses: Hypothesis[] }>(`/incidents/${incidentId}/hypotheses`);
  }

  // Test a single hypothesis in sandbox
  async testHypothesis(incidentId: string, hypothesisId: string) {
    return this.request<{
      incident_id: string;
      hypothesis_id: string;
      id: string;
      title: string;
      causal_claim: string;
      intervention: string;
      status: "CONFIRMED" | "REFUTED";
      reproduction_rate: number;
      hypothesis_supported: boolean;
      failure_oracle: any;
      metrics: any;
      trajectory?: TrajectoryPoint[];
      trajectories?: any[];
      message: string;
    }>(`/incidents/${incidentId}/hypotheses/${hypothesisId}/test`, { method: "POST" });
  }

  // Get incident experiments
  getExperiments(incidentId: string) {
    return this.requestDeduped<{ incident_id: string; count: number; experiments: Experiment[] }>(`/incidents/${incidentId}/experiments`);
  }

  // The calibrated incident model - the numbers every prediction is made from
  getSystemModel(incidentId: string) {
    return this.requestDeduped<IncidentSystemModel>(`/incidents/${incidentId}/system-model`);
  }

  // Get incident patches
  getPatches(incidentId: string) {
    return this.requestDeduped<{ incident_id: string; count: number; patch_candidates: PatchCandidate[]; verification_reports: VerificationReport[] }>(`/incidents/${incidentId}/patches`);
  }

  // Generate / export standalone installer script or diff
  async exportPatch(incidentId: string, format: string = "installer"): Promise<string | Blob> {
    const url = `${this.baseUrl}/incidents/${incidentId}/export-patch?format=${format}`;
    const { accessToken } = useAuthStore.getState();
    const headers: Record<string, string> = {};
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    const response = await fetch(url, { headers });

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        if (typeof errorData.detail === 'string') {
          errorMessage = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          errorMessage = errorData.detail.map((d: any) => (d && typeof d === 'object' ? d.msg || d.message : String(d))).join(', ');
        } else if (errorData.detail && typeof errorData.detail === 'object') {
          errorMessage = errorData.detail.msg || errorData.detail.message || JSON.stringify(errorData.detail);
        } else if (typeof errorData.error === 'string') {
          errorMessage = errorData.error;
        }
      } catch {}
      throw new Error(errorMessage);
    }

    if (format.toLowerCase() === "zip") {
      return response.blob();
    }
    return response.text();
  }

  // Download patch package as blob for file download
  async downloadPatchPackage(incidentId: string): Promise<Blob> {
    const { accessToken } = useAuthStore.getState();
    const headers: Record<string, string> = {};
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }

    const response = await fetch(`${this.baseUrl}/incidents/${incidentId}/download-patch-package`, { headers });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to download patch package: ${response.status} ${errorText}`);
    }

    return response.blob();
  }

  // Run experiment (ghost-lab endpoint)
  async runExperiment(incidentId: string) {
    return this.request<{ incident_id: string; count: number; experiments: Experiment[]; message: string }>(`/incidents/${incidentId}/experiments/run`, { method: "POST" });
  }

  // Interactive custom simulation for Engineer Mode
  async simulateCustom(
    incidentId: string,
    params: {
      batching_window_ms?: number;
      qos_queue_depth?: number;
      clock_skew_ms?: number;
      max_batch_size?: number;
      gpu_contention_ms?: number;
      freshness_budget_ms?: number;
      trials?: number;
    }
  ) {
    return this.request<{
      incident_id: string;
      trial_count: number;
      reproduction_count: number;
      reproduction_rate: number;
      avg_latency_ms: number;
      p99_latency_ms: number;
      freshness_budget_ms: number;
      emergency_stop_triggered: boolean;
      hypothesis_supported: boolean;
      status: "CONFIRMED" | "REFUTED";
      parameters: any;
      cycles: any[];
      trajectory?: TrajectoryPoint[];
      trajectories?: any[];
      message: string;
    }>(`/incidents/${incidentId}/simulate-custom`, {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  // Reconstruct incident pipeline
  async reconstruct(incidentId: string) {
    return this.request<{ message: string; incident_id: string }>(`/incidents/${incidentId}/reconstruct`, { method: "POST" });
  }

  // Get incident report
  async getReport(incidentId: string): Promise<IncidentReport> {
    return this.request<IncidentReport>(`/incidents/${incidentId}/report`);
  }

  // Export report as JSON
  async exportReport(incidentId: string): Promise<IncidentReport> {
    return this.request<IncidentReport>(`/incidents/${incidentId}/report`);
  }

  // List reports for an incident
  async listReports(incidentId: string): Promise<{ reports: Array<{ id: string; incident_id: string; title: string; generated_at: string; size_bytes: number; format: string; status: string; type: string }> }> {
    return this.request<{ reports: Array<{ id: string; incident_id: string; title: string; generated_at: string; size_bytes: number; format: string; status: string; type: string }> }>(`/incidents/${incidentId}/reports`);
  }

  // Delete an incident report
  async deleteReport(incidentId: string, reportId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/incidents/${incidentId}/reports/${reportId}`, {
      method: "DELETE"
    });
  }

  // Apply patch to target directory
  async applyPatch(incidentId: string, targetDir: string = ".", dryRun: boolean = false, rollback: boolean = false): Promise<ApplyPatchResult> {
    return this.request<ApplyPatchResult>(`/incidents/${incidentId}/apply-patch`, {
      method: "POST",
      body: JSON.stringify({ target_directory: targetDir, dry_run: dryRun, rollback })
    });
  }

  // Get temporal visualization data
  async getTemporalVisualization(incidentId: string): Promise<TemporalVisualizationResponse> {
    return this.request(`/incidents/${incidentId}/temporal-visualization`);
  }

  // Real before/after digital-twin comparison (re-runs the twin both sides)
  async getVictoryReplay(incidentId: string): Promise<VictoryReplayResponse> {
    return this.requestDeduped<VictoryReplayResponse>(`/incidents/${incidentId}/victory-replay`);
  }

  // Get holographic reconstruction data
  getHolographicReconstruction(
    incidentId: string,
    options: {
      enable_counterfactual?: boolean;
      enable_anomalies?: boolean;
      enable_multiscale?: boolean;
      use_gpu?: boolean;
      gpu_decay_type?: string;
      gpu_normalization?: string;
      gpu_time_step_ns?: number;
      gpu_max_kernel_time_ns?: number;
    } = {}
  ): Promise<HolographicData> {
    const params = new URLSearchParams();
    // Backend declares `incident_id` (FastAPI Query), not `incidentId`.
    params.append('incident_id', incidentId);
    if (options.enable_counterfactual !== undefined) params.append('enable_counterfactual', options.enable_counterfactual.toString());
    if (options.enable_anomalies !== undefined) params.append('enable_anomalies', options.enable_anomalies.toString());
    if (options.enable_multiscale !== undefined) params.append('enable_multiscale', options.enable_multiscale.toString());
    if (options.use_gpu !== undefined) params.append('use_gpu', options.use_gpu.toString());
    if (options.gpu_decay_type) params.append('gpu_decay_type', options.gpu_decay_type);
    if (options.gpu_normalization) params.append('gpu_normalization', options.gpu_normalization);
    if (options.gpu_time_step_ns) params.append('gpu_time_step_ns', options.gpu_time_step_ns.toString());
    if (options.gpu_max_kernel_time_ns) params.append('gpu_max_kernel_time_ns', options.gpu_max_kernel_time_ns.toString());

    // The backend returns the VisualizationResponse object itself (no {data:...} envelope).
    return this.requestDeduped<HolographicData>(`/holographic/reconstruction?${params.toString()}`);
  }

  // Model Gateway Management
  async getModelHealth(): Promise<{
    status: string;
    provider: string;
    mode: string;
    cloud_credentials_required: boolean;
    nebius_configured: boolean;
    masked_key: string;
    base_url?: string;
    model_fast?: string;
    model_reasoning?: string;
    model_escalation?: string;
    timestamp: string;
  }> {
    return this.request('/model-health');
  }

  async configureModel(config: {
    apiKey?: string;
    baseUrl?: string;
    modelFast?: string;
    modelReasoning?: string;
    modelEscalation?: string;
    provider?: string;
  }): Promise<{
    status: string;
    configured: boolean;
    masked_key: string;
    base_url: string;
    model_fast: string;
    model_reasoning: string;
    model_escalation: string;
    provider: string;
    message: string;
  }> {
    return this.request('/model/configure', {
      method: 'POST',
      body: JSON.stringify({
        api_key: config.apiKey,
        base_url: config.baseUrl,
        model_fast: config.modelFast,
        model_reasoning: config.modelReasoning,
        model_escalation: config.modelEscalation,
        provider: config.provider,
      }),
    });
  }

  async clearModelConfig(): Promise<{
    status: string;
    configured: boolean;
    masked_key: string;
    provider: string;
    message: string;
  }> {
    return this.request('/model/configure', {
      method: 'DELETE',
    });
  }

  async testModelConnection(config?: {
    apiKey?: string;
    baseUrl?: string;
    model?: string;
  }): Promise<{
    success: boolean;
    provider?: string;
    mode?: string;
    latency_ms: number;
    models_available?: number;
    error?: string;
    message: string;
  }> {
    return this.request('/model/test', {
      method: 'POST',
      body: config ? JSON.stringify({
        api_key: config.apiKey,
        base_url: config.baseUrl,
        model: config.model,
      }) : undefined,
    });
  }
}

export const api = new ApiClient();