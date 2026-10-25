/**
 * Shared Victory Replay test fixture.
 *
 * The payload mirrors the *real* shape returned by
 * `GET /api/v1/incidents/{incident_id}/victory-replay`, which itself comes from
 * `CloudToRobotDigitalTwin.compare_configurations()` running both sides of the
 * digital twin over identical seeds. Nothing here is a number the component
 * invents — it is exactly what the backend measures.
 */
export const victoryReplayFixture = {
  incident_id: "CAU-0001",
  available: true,
  experiment: {
    experiment_id: "exp-h1",
    hypothesis_id: "h1",
    branch_name: "exp-h1",
    intervention: "config/inference.yaml: batching_window_ms = 100",
    conclusion:
      "Batching window reduced from 200ms to 100ms; failure eliminated in the twin.",
    reproduction_rate: 1.0,
  },
  applied_configuration: { batching_window_ms: "100" },
  freshness_budget_ms: 120,
  verdict: {
    failure_eliminated: true,
    regression_introduced: false,
    improvement: true,
  },
  delta: {
    reproduction_rate: -1.0,
    avg_latency_ms: -52.0,
    p99_latency_ms: -52.0,
    max_latency_ms: null,
    avg_batch_wait_ms: -52.0,
    avg_gpu_compute_ms: 0,
    avg_network_delay_ms: 0,
    goal_reached_count: 20,
  },
  before: {
    trial_count: 20,
    reproduction_count: 20,
    reproduction_rate: 1.0,
    avg_latency_ms: 158.04,
    p99_latency_ms: 162.23,
    max_latency_ms: 164.0,
    avg_batch_wait_ms: 103.87,
    avg_gpu_compute_ms: 46.5,
    avg_network_delay_ms: 14.0,
    goal_reached_count: 0,
    emergency_stop_count: 20,
    is_confirmed_safe: false,
    halt_reason: "stale-perception",
    stop_coordinate: { x: 12.4, y: 0 },
    parameters: {
      batching_window_ms: 200,
      qos_queue_depth: 10,
      clock_skew_ms: 0,
      max_batch_size: 8,
      gpu_contention_ms: 0,
      freshness_budget_ms: 120,
    },
    trajectory: [
      {
        t: 0, x: 0.0, y: 0, v: 0.0, latency_ms: 103.87,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 103.87, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 1, x: 4.0, y: 0, v: 1.2, latency_ms: 130.0,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 104.0, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 2, x: 8.0, y: 0, v: 1.4, latency_ms: 150.5,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 104.0, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 3, x: 12.4, y: 0, v: 1.3, latency_ms: 158.04,
        status: "EMERGENCY_STOP", is_stale: true, emergency_stop: true,
        batch_wait_ms: 103.79, gpu_compute_ms: 27.0, network_delay_ms: 14.0,
      },
    ],
    trajectories: [
      {
        path: [
          {
            t: 0, x: 0.0, y: 0, v: 0.0, latency_ms: 103.87,
            status: "NOMINAL", is_stale: false, emergency_stop: false,
          },
          {
            t: 3, x: 12.4, y: 0, v: 1.3, latency_ms: 158.04,
            status: "EMERGENCY_STOP", is_stale: true, emergency_stop: true,
          },
        ],
        final_status: "EMERGENCY_STOP",
        is_confirmed_safe: false,
        stop_coordinate: { x: 12.4, y: 0 },
        halt_reason: "stale-perception",
        distance_traveled_m: 12.4,
      },
    ],
  },
  after: {
    trial_count: 20,
    reproduction_count: 0,
    reproduction_rate: 0.0,
    avg_latency_ms: 106.04,
    p99_latency_ms: 110.23,
    max_latency_ms: 112.0,
    avg_batch_wait_ms: 51.87,
    avg_gpu_compute_ms: 46.5,
    avg_network_delay_ms: 14.0,
    goal_reached_count: 20,
    emergency_stop_count: 0,
    is_confirmed_safe: true,
    halt_reason: null,
    stop_coordinate: null,
    parameters: {
      batching_window_ms: 100,
      qos_queue_depth: 10,
      clock_skew_ms: 0,
      max_batch_size: 8,
      gpu_contention_ms: 0,
      freshness_budget_ms: 120,
    },
    trajectory: [
      {
        t: 0, x: 0.0, y: 0, v: 0.0, latency_ms: 51.87,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 51.87, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 1, x: 6.0, y: 0, v: 1.4, latency_ms: 88.0,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 52.0, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 2, x: 12.0, y: 0, v: 1.4, latency_ms: 102.0,
        status: "NOMINAL", is_stale: false, emergency_stop: false,
        batch_wait_ms: 52.0, gpu_compute_ms: 26.0, network_delay_ms: 14.0,
      },
      {
        t: 3, x: 24.0, y: 0, v: 1.4, latency_ms: 106.04,
        status: "GOAL_REACHED", is_stale: false, emergency_stop: false,
        batch_wait_ms: 51.76, gpu_compute_ms: 27.0, network_delay_ms: 14.0,
      },
    ],
    trajectories: [
      {
        path: [
          {
            t: 0, x: 0.0, y: 0, v: 0.0, latency_ms: 51.87,
            status: "NOMINAL", is_stale: false, emergency_stop: false,
          },
          {
            t: 3, x: 24.0, y: 0, v: 1.4, latency_ms: 106.04,
            status: "GOAL_REACHED", is_stale: false, emergency_stop: false,
          },
        ],
        final_status: "GOAL_REACHED",
        is_confirmed_safe: true,
        stop_coordinate: { x: 24.0, y: 0 },
        halt_reason: null,
        distance_traveled_m: 24.0,
      },
    ],
  },
  patch: {
    id: "patch-001",
    candidate_id: "PATCH-001",
    title: "Reduce batching window to 100ms",
    score: 0.97,
    verified: true,
    unified_diff:
      "--- a/cauveris/config/inference.yaml\n" +
      "+++ b/cauveris/config/inference.yaml\n" +
      "@@ -1,3 +1,3 @@\n" +
      "-  batching_window_ms: 200\n" +
      "+  batching_window_ms: 100",
    diff: "",
    affected_files: ["cauveris/config/inference.yaml"],
    lines_changed: 1,
    rationale:
      "Reducing the cloud-side batching window from 200ms to 100ms halves perception " +
      "detection latency under load, restoring the freshness budget.",
    applied_cleanly: true,
    regression_test_passes_after: true,
    original_failure_not_reproduced: true,
    existing_tests_pass: true,
    safety_invariants_pass: true,
    performance_within_budget: true,
    forbidden_change_scan_passes: true,
    rollback_test_passes: true,
  },
  verification: {
    passed: true,
    message:
      "Patch PATCH-001 verified: 9/9 invariant gates passed across 20 twin trials.",
    applies_cleanly: true,
    regression_test_fails_before: true,
    regression_test_passes_after: true,
    original_failure_not_reproduced: true,
    existing_tests_pass: true,
    safety_invariants_pass: true,
    performance_within_budget: true,
    forbidden_change_scan_passes: true,
    rollback_test_passes: true,
    verified: true,
  },
};

/** Result shape the backend returns from the real rollback path. */
export const applyPatchSuccessFixture = {
  success: true,
  message: "Rollback verified: patch is cleanly reversible",
  applied: true,
  dry_run: true,
  status: "rollback_verified",
};
