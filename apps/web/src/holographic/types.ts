/**
 * Holographic Reconstruction - Core Type Definitions
 * Based on Cauveris Holographic Reconstruction Plan (Phase 1-4)
 */

export type NodeType = "event" | "decision" | "condition" | "action" | "service" | "database" | "cache" | "gateway" | "message_queue" | "monitoring";
export type LinkType = "causes" | "enables" | "inhibits" | "correlates" | "causal" | "network";

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

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

export interface AmbiguityRegionData {
  component: string;
  dimension: string;
  affected_dimensions: string[];
  time_range_ns: [number, number];
  duration_ms: number;
  ambiguity_score: number;
  missing_layers: string[];
  description: string;
  severity: "low" | "medium" | "high";
}
