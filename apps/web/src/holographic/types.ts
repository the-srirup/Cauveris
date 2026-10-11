/**
 * Holographic Reconstruction - Core Type Definitions
 * Aligned with backend VisualizationData from cauveris/holographic/visualization.py
 * and VisualizationResponse from cauveris/api/holographic.py
 */

export type NodeType = "service" | "database" | "cache" | "gateway" | "message_queue" | "monitoring";
export type LinkType = "causal" | "network" | "causes" | "enables" | "inhibits" | "correlates";
export type ComponentType = "service" | "database" | "cache" | "gateway" | "message_queue";
export type AnomalySeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type BoundaryLayer = "APPLICATION_LOG" | "METRICS_EXPORT" | "DISTRIBUTED_TRACE" | "NETWORK_FLOW" | "INFRASTRUCTURE_LOG";
export type ScaleName = "MICRO" | "MESO" | "MACRO";

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export interface BulkNode {
  id: string;
  name: string;
  type: ComponentType;
  position: [number, number, number]; // x, y, z
  size: number;
  color: string;
  health: number; // [0, 1]
  metrics: {
    cpu_usage: number;
    memory_usage: number;
    network_usage: number;
    error_rate: number;
    latency_p99_ms: number;
  };
  confidence: number; // [0, 1]
  config_changed: boolean;
}

export interface BulkEdge {
  source: string;
  target: string;
  type: LinkType;
  thickness: number;
  color: string;
  latency_ms: number;
  source_health: number;
  target_health: number;
  loss_rate?: number;
  bandwidth_mbps?: number;
}

export interface BoundaryLayerData {
  layer: BoundaryLayer;
  component: string;
  num_heus: number;
  signals: Record<string, { value: number; count: number; min: number; max: number }>;
  encoded_dimensions: Record<string, number>;
  reconstruction_weight: number;
  ambiguity_score: number;
  synthesized_ratio: number;
  color: string;
}

export interface BoundaryLayers {
  [componentId: string]: Record<BoundaryLayer, BoundaryLayerData>;
}

export interface ScaleHierarchyItem {
  scale: ScaleName;
  time_window_ns: [number, number];
  fidelity: number;
  num_components: number;
  prior_chained: boolean;
}

export interface AmbiguityRegionData {
  component: string;
  dimension: string;
  affected_dimensions: string[];
  time_range_ns: [number, number];
  duration_ms: number;
  ambiguity_score: number;
  missing_layers: BoundaryLayer[];
  description: string;
  primary_value: number;
  ci_lower: number;
  ci_upper: number;
  ci_width: number;
  entropy: number;
  num_alternatives: number;
  alternatives: any[];
  severity: "low" | "medium" | "high";
}

export interface CounterfactualChange {
  component: string;
  dimension: string;
  original: number;
  intervened: number;
  change: number;
  improvement: boolean;
}

export interface CounterfactualData {
  intervention: string;
  intervention_type: string;
  fidelity_improvement: number;
  cost_estimate: number;
  risk_score: number;
  changes: CounterfactualChange[];
  predicted_boundary: Record<string, any>;
}

export interface AnomalyData {
  component: string;
  type: string;
  severity: AnomalySeverity;
  score: number;
  description: string;
  timestamp_ns: number;
  affected_dimensions: string[];
  boundary_layers: BoundaryLayer[];
  expected_value: number;
  observed_value: number;
  deviation: number;
}

export interface VisualizationMetadata {
  overall_fidelity: number;
  boundary_residual: number;
  num_components: number;
  num_ambiguity_regions: number;
  time_window_ns: number;
  generation_timestamp_ns: number;
}

export interface VisualizationResponse {
  incident_id: string;
  bulk_nodes: BulkNode[];
  bulk_edges: BulkEdge[];
  boundary_layers: BoundaryLayers;
  scale_hierarchy: ScaleHierarchyItem[];
  ambiguity_regions: AmbiguityRegionData[];
  counterfactual: CounterfactualData | null;
  anomalies: AnomalyData[];
  metadata: VisualizationMetadata;
}

// Legacy types for backward compatibility with existing hook code
export interface CausalNode {
  id: string;
  label: string;
  name?: string;
  type: NodeType;
  position: Vec3;
  velocity?: Vec3;
  radius: number;
  color: string;
  health: number; // [0, 1]
  metrics?: {
    cpu_usage: number;
    memory_usage: number;
    network_usage: number;
    error_rate: number;
    latency_p99_ms: number;
  };
  confidence?: number;
  config_changed?: boolean;
  metadata?: Record<string, any>;
  fixed?: boolean;
  layer?: number; // Topological layer (DAG)
  fx?: number | null;
  fy?: number | null;
  fz?: number | null;
  x?: number;
  y?: number;
  z?: number;
}

export interface CausalLink {
  source: string;
  target: string;
  strength: number; // causal weight [0, 1]
  type: LinkType;
  directional?: boolean;
  latency_ms?: number;
  source_health?: number;
  target_health?: number;
  loss_rate?: number;
  bandwidth_mbps?: number;
  metadata?: Record<string, any>;
}

export interface CausalGraph {
  nodes: CausalNode[];
  links: CausalLink[];
}

export interface TemporalFrame {
  stageId: string;
  timestamp: number;
  nodes: CausalNode[];
  links: CausalLink[];
  phaseMap?: Float32Array;
  amplitudeTarget?: Float32Array;
}

export interface QualityMetrics {
  mse: number;
  ssim: number;
  strehlRatio: number;
  iterations: number;
}

export interface HologramState {
  phaseMap: Float32Array | null;
  amplitudeTarget: Float32Array | null;
  quality: QualityMetrics;
  sliceZ: number;
  isComputing: boolean;
  wavelength: number; // meters (e.g. 532e-9)
  pixelPitch: number; // meters (e.g. 8e-6)
  gridSize: number; // e.g. 512 or 1024
}

// SCM Structural Causal Model types
export interface SCMNode {
  id: string;
  parents: string[];
  structuralFn?: (parentValues: number[], noise: number) => number;
  valueFactual: number;
  noise: number; // abducted noise
  valueCounterfactual: number;
  observedStd: number;
}

export interface NodeDiff {
  nodeId: string;
  positionDelta: Vec3;
  valueDelta: number;
  attribution: number;
  type: "added" | "removed" | "modified" | "unchanged";
}

export interface CounterfactualResult {
  interventionNode: string;
  interventionValue: number;
  factualValues: Record<string, number>;
  counterfactualValues: Record<string, number>;
  attribution: Record<string, number>;
  ghostPositions: Record<string, Vec3>;
  diff: NodeDiff[];
}

// Graph Mutations for Patches
export type GraphMutation =
  | { kind: "addNode"; node: CausalNode }
  | { kind: "removeNode"; id: string }
  | { kind: "addEdge"; link: CausalLink }
  | { kind: "removeEdge"; source: string; target: string }
  | {
      kind: "modifyEdge";
      source: string;
      target: string;
      before: { strength: number };
      after: { strength: number };
    };

export interface ForceLayoutConfig {
  manyBodyStrength: number;
  manyBodyTheta: number;
  manyBodyDistanceMin: number;
  manyBodyDistanceMax: number;
  linkStrength?: number;
  linkDistance: number;
  collisionRadius: number;
  collisionStrength: number;
  collisionIterations: number;
  dagMode: "zout" | "zin" | "radial" | "none";
  dagLevelDistance: number;
  alphaDecay: number;
  velocityDecay: number;
  alphaMin: number;
  centerStrength: number;
}

// Helper functions for converting between legacy and new types
export function bulkNodeToCausalNode(bulkNode: BulkNode): CausalNode {
  return {
    id: bulkNode.id,
    label: bulkNode.name,
    name: bulkNode.name,
    type: bulkNode.type as NodeType,
    position: { x: bulkNode.position[0], y: bulkNode.position[1], z: bulkNode.position[2] },
    radius: bulkNode.size,
    color: bulkNode.color,
    health: bulkNode.health,
    metrics: bulkNode.metrics,
    confidence: bulkNode.confidence,
    config_changed: bulkNode.config_changed,
  };
}

export function bulkEdgeToCausalLink(bulkEdge: BulkEdge): CausalLink {
  return {
    source: bulkEdge.source,
    target: bulkEdge.target,
    strength: 1.0, // Not directly available, default
    type: bulkEdge.type,
    latency_ms: bulkEdge.latency_ms,
    source_health: bulkEdge.source_health,
    target_health: bulkEdge.target_health,
    loss_rate: bulkEdge.loss_rate,
    bandwidth_mbps: bulkEdge.bandwidth_mbps,
  };
}

export function visualizationResponseToCausalGraph(response: VisualizationResponse): CausalGraph {
  return {
    nodes: response.bulk_nodes.map(bulkNodeToCausalNode),
    links: response.bulk_edges.map(bulkEdgeToCausalLink),
  };
}