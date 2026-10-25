/**
 * Fixture mirroring the real `GET /incidents/{id}/temporal-visualization`
 * payload, derived from the golden incident (CAU-0001).
 *
 * The real endpoint returns 51 evidence events, 112 causal edges across 9
 * lanes, and a 17-step safety chain from the batching-window change to the
 * emergency stop. The fixture below is a faithful subset so the tests
 * exercise the same code paths as production data.
 */
export const temporalVisualizationFixture = {
  events: [
    {
      id: "deployment_json:deployments/events.json#000000.454c409b",
      ts: 0,
      domain: "host",
      label: "Deployment v42 applied to inference-service",
      merge_group: "deployments/events.json@1789891200000",
      confidence: 1,
      lane: "deployment_events",
      source: "deployments/events.json",
      source_type: "deployment_json",
      message: "Deployment v42 applied to inference-service",
      clock_domain: "host",
      attributes: { deployment_id: "v42", service: "inference-service" },
    },
    {
      id: "jsonl_log:logs/cloud-service.jsonl#000000.470c566e",
      ts: 8990.0,
      domain: "cloud",
      label: "[cloud-service] Inference worker batch window set to 200ms by deployment",
      merge_group: "logs/cloud-service.jsonl@1789900190000",
      confidence: 1,
      lane: "cloud_requests",
      source: "logs/cloud-service.jsonl",
      source_type: "jsonl_log",
      message: "[cloud-service] Inference worker batch window set to 200ms by deployment",
      clock_domain: "robot",
      attributes: { node: "cloud-service", level: "INFO" },
    },
    {
      id: "otel_trace:traces/otel.json#000000.3c8b3569",
      ts: 8990.1,
      domain: "cloud",
      label: "Trace span 'inference_request' (duration: 155.0ms)",
      merge_group: "traces/otel.json@1789900190100",
      confidence: 0.95,
      lane: "cloud_requests",
      source: "traces/otel.json",
      source_type: "otel_trace",
      message: "Trace span 'inference_request' (duration: 155.0ms)",
      clock_domain: "cloud",
      attributes: {
        span_name: "inference_request",
        duration_ms: 155,
        queue_wait_ms: 115,
        "batch.window_ms": 200,
        freshness_budget_ms: 120,
      },
    },
    {
      id: "mcap_recording:recordings/robot_run.mcap#000002.e80931fb",
      ts: 8990.21,
      domain: "robot",
      label: "Received 1 detections (age: 155.0ms)",
      merge_group: "recordings/robot_run.mcap@1789900190210",
      confidence: 0.9,
      lane: "detection_publication",
      source: "recordings/robot_run.mcap",
      source_type: "mcap_recording",
      message: "Received 1 detections (age: 155.0ms)",
      clock_domain: "robot",
      attributes: { topic: "/detections" },
    },
    {
      id: "jsonl_log:logs/ros-nodes.jsonl#000001.855b7572",
      ts: 8990.22,
      domain: "robot",
      label: "[navigation_controller] Transform lookup failed: stale detections",
      merge_group: "logs/ros-nodes.jsonl@1789900190220",
      confidence: 0.9,
      lane: "tf_events",
      source: "logs/ros-nodes.jsonl",
      source_type: "jsonl_log",
      message: "[navigation_controller] Transform lookup failed: stale detections",
      clock_domain: "robot",
      attributes: { node: "navigation_controller", level: "ERROR" },
    },
    {
      id: "jsonl_log:logs/ros-nodes.jsonl#000002.7fd4cba1",
      ts: 8990.27,
      domain: "robot",
      label: "[safety_monitor] Emergency stop triggered: control deadline missed",
      merge_group: "logs/ros-nodes.jsonl@1789900190270",
      confidence: 1,
      lane: "safety_state",
      source: "logs/ros-nodes.jsonl",
      source_type: "jsonl_log",
      message: "[safety_monitor] Emergency stop triggered: control deadline missed",
      clock_domain: "robot",
      attributes: { node: "safety_monitor", level: "CRITICAL" },
    },
    {
      id: "mcap_recording:recordings/robot_run.mcap#000005.baea0244",
      ts: 8990.27,
      domain: "robot",
      label: "EMERGENCY_STOP_TRIGGERED: control deadline missed due to stale perception",
      merge_group: "recordings/robot_run.mcap@1789900190270",
      confidence: 1,
      lane: "safety_state",
      source: "recordings/robot_run.mcap",
      source_type: "mcap_recording",
      message: "EMERGENCY_STOP_TRIGGERED: control deadline missed due to stale perception",
      clock_domain: "robot",
      attributes: { topic: "/safety_status" },
    },
  ],
  connections: [
    {
      source: "deployment_json:deployments/events.json#000000.454c409b",
      target: "jsonl_log:logs/cloud-service.jsonl#000000.470c566e",
      provenance: "deployment_chain",
      type: "causal_edge",
    },
    {
      source: "jsonl_log:logs/cloud-service.jsonl#000000.470c566e",
      target: "otel_trace:traces/otel.json#000000.3c8b3569",
      provenance: "temporal_proximity",
      type: "causal_edge",
    },
    {
      source: "otel_trace:traces/otel.json#000000.3c8b3569",
      target: "mcap_recording:recordings/robot_run.mcap#000002.e80931fb",
      provenance: "cross_domain_handoff",
      type: "causal_edge",
    },
    {
      source: "mcap_recording:recordings/robot_run.mcap#000002.e80931fb",
      target: "jsonl_log:logs/ros-nodes.jsonl#000001.855b7572",
      provenance: "cross_domain_handoff",
      type: "causal_edge",
    },
    {
      source: "jsonl_log:logs/ros-nodes.jsonl#000001.855b7572",
      target: "jsonl_log:logs/ros-nodes.jsonl#000002.7fd4cba1",
      provenance: "log_node_order",
      type: "causal_edge",
    },
    {
      source: "jsonl_log:logs/ros-nodes.jsonl#000002.7fd4cba1",
      target: "mcap_recording:recordings/robot_run.mcap#000005.baea0244",
      provenance: "temporal_proximity",
      type: "causal_edge",
    },
  ],
  anomaly_points: [
    {
      id: "/cmd_vel",
      type: "co_temporal_ambiguity",
      severity: 0.8,
      confidence: 1,
      explanation:
        "E-stop command and safety status logged at same instant - order undecidable (topics: ['/safety_status', '/cmd_vel'])",
    },
    {
      id: "/detections",
      type: "latency_budget_breach",
      severity: 0.9,
      confidence: 1,
      explanation: "Detection age 155.0ms exceeded 120ms freshness budget",
    },
  ],
  untrusted_bands: [
    {
      start_s: 8990.27,
      end_s: 8990.27,
      reason: "co_temporal_ambiguity",
      description: "Events at this instant span multiple clock domains",
    },
  ],
  causal_chains: [
    {
      terminal_id: "mcap_recording:recordings/robot_run.mcap#000005.baea0244",
      terminal_lane: "safety_state",
      terminal_message:
        "EMERGENCY_STOP_TRIGGERED: control deadline missed due to stale perception",
      terminal_source: "recordings/robot_run.mcap",
      terminal_domain: "robot",
      is_safety_outcome: true,
      length: 6,
      steps: [
        {
          source: "deployment_json:deployments/events.json#000000.454c409b",
          target: "jsonl_log:logs/cloud-service.jsonl#000000.470c566e",
          provenance: "deployment_chain",
          source_lane: "deployment_events",
          target_lane: "cloud_requests",
          source_message: "Deployment v42 applied to inference-service",
          target_message:
            "[cloud-service] Inference worker batch window set to 200ms by deployment",
        },
        {
          source: "jsonl_log:logs/cloud-service.jsonl#000000.470c566e",
          target: "otel_trace:traces/otel.json#000000.3c8b3569",
          provenance: "temporal_proximity",
          source_lane: "cloud_requests",
          target_lane: "cloud_requests",
          source_message:
            "[cloud-service] Inference worker batch window set to 200ms by deployment",
          target_message: "Trace span 'inference_request' (duration: 155.0ms)",
        },
        {
          source: "otel_trace:traces/otel.json#000000.3c8b3569",
          target: "mcap_recording:recordings/robot_run.mcap#000002.e80931fb",
          provenance: "cross_domain_handoff",
          source_lane: "cloud_requests",
          target_lane: "detection_publication",
          source_message: "Trace span 'inference_request' (duration: 155.0ms)",
          target_message: "Received 1 detections (age: 155.0ms)",
        },
        {
          source: "mcap_recording:recordings/robot_run.mcap#000002.e80931fb",
          target: "jsonl_log:logs/ros-nodes.jsonl#000001.855b7572",
          provenance: "cross_domain_handoff",
          source_lane: "detection_publication",
          target_lane: "tf_events",
          source_message: "Received 1 detections (age: 155.0ms)",
          target_message:
            "[navigation_controller] Transform lookup failed: stale detections",
        },
        {
          source: "jsonl_log:logs/ros-nodes.jsonl#000001.855b7572",
          target: "jsonl_log:logs/ros-nodes.jsonl#000002.7fd4cba1",
          provenance: "log_node_order",
          source_lane: "tf_events",
          target_lane: "safety_state",
          source_message:
            "[navigation_controller] Transform lookup failed: stale detections",
          target_message:
            "[safety_monitor] Emergency stop triggered: control deadline missed",
        },
        {
          source: "jsonl_log:logs/ros-nodes.jsonl#000002.7fd4cba1",
          target: "mcap_recording:recordings/robot_run.mcap#000005.baea0244",
          provenance: "temporal_proximity",
          source_lane: "safety_state",
          target_lane: "safety_state",
          source_message:
            "[safety_monitor] Emergency stop triggered: control deadline missed",
          target_message:
            "EMERGENCY_STOP_TRIGGERED: control deadline missed due to stale perception",
        },
      ],
    },
  ],
  lanes: [
    {
      lane: "deployment_events",
      tier: 0,
      event_count: 1,
      domains: ["host"],
      sources: ["deployments/events.json"],
      start_s: 0,
      end_s: 0,
      first_message: "Deployment v42 applied to inference-service",
      last_message: "Deployment v42 applied to inference-service",
    },
    {
      lane: "cloud_requests",
      tier: 1,
      event_count: 12,
      domains: ["cloud", "robot"],
      sources: ["logs/cloud-service.jsonl", "metrics/gpu.csv", "traces/otel.json"],
      start_s: 8990.0,
      end_s: 8990.3,
      first_message:
        "[cloud-service] Inference worker batch window set to 200ms by deployment",
      last_message: "Metric inference_latency_ms: 190.0",
    },
    {
      lane: "detection_publication",
      tier: 2,
      event_count: 2,
      domains: ["robot"],
      sources: ["logs/ros-nodes.jsonl", "recordings/robot_run.mcap"],
      start_s: 8990.21,
      end_s: 8990.21,
      first_message: "Received 1 detections (age: 155.0ms)",
      last_message:
        "[detection_listener] Received detection message from cloud inference",
    },
    {
      lane: "tf_events",
      tier: 3,
      event_count: 3,
      domains: ["robot"],
      sources: ["logs/ros-nodes.jsonl", "recordings/robot_run.mcap"],
      start_s: 8990.0,
      end_s: 8990.26,
      first_message: "MCAP topic /tf",
      last_message:
        "ExtrapolationException: Transform lookup from base_link to odom failed",
    },
    {
      lane: "safety_state",
      tier: 4,
      event_count: 3,
      domains: ["host", "robot"],
      sources: ["logs/ros-nodes.jsonl", "observations/operator_note.md", "recordings/robot_run.mcap"],
      start_s: 8990.27,
      end_s: 9000.0,
      first_message:
        "[safety_monitor] Emergency stop triggered: control deadline missed",
      last_message:
        "Operator observed AMR-01 sudden emergency stop in aisle B",
    },
  ],
  lane_edges: [
    {
      source: "deployment_events",
      target: "cloud_requests",
      edge_count: 12,
      provenance: { deployment_chain: 12 },
    },
    {
      source: "cloud_requests",
      target: "detection_publication",
      edge_count: 10,
      provenance: { cross_domain_handoff: 10 },
    },
    {
      source: "detection_publication",
      target: "tf_events",
      edge_count: 3,
      provenance: { cross_domain_handoff: 3 },
    },
    {
      source: "tf_events",
      target: "safety_state",
      edge_count: 1,
      provenance: { log_node_order: 1 },
    },
  ],
  summary: {
    total_events: 7,
    connections: 6,
    anomaly_count: 2,
    time_loop_count: 0,
    is_anomalous: true,
    confidence: 0.2,
    causal_edge_count: 6,
    violation_count: 0,
    provenance_breakdown: {
      deployment_chain: 1,
      temporal_proximity: 2,
      cross_domain_handoff: 2,
      log_node_order: 1,
    },
    chain_count: 1,
    lane_count: 5,
  },
};

/**
 * A hypothesis payload with no fabricated fallback — the page must render an
 * honest empty state when the backend has not produced hypotheses.
 */
export const causalHypothesesFixture = {
  incident_id: "CAU-0001",
  count: 1,
  hypotheses: [
    {
      id: "h1_batching_window",
      hypothesis_id: "h1_batching_window",
      title: "H1: Dynamic Batching Window Increase",
      causal_claim:
        "Increased dynamic batching window in deployment v42 caused inference latency to exceed the robot freshness budget (120ms), producing stale detections that triggered emergency stop",
      description:
        "Increased dynamic batching window in deployment v42 caused inference latency to exceed the robot freshness budget (120ms), producing stale detections that triggered emergency stop",
      confidence: 92,
      confidence_prior: 0.92,
      status: "INFERRED",
      intervention:
        "Reduce dynamic batching window from 200ms to 100ms in config/inference.yaml",
      supporting_artifact_ids: [
        "deployments/events.json",
        "config/inference.yaml",
        "traces/otel.json",
        "metrics/gpu.csv",
      ],
      contradicting_artifact_ids: [],
      missing_evidence: ["Per-client latency breakdown across batch sizes"],
    },
  ],
};
