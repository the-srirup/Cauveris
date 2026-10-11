/**
 * Incident Comparison Component - Side-by-side 3D holographic views
 */

import React, { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import {
  VisualizationResponse,
  BulkNode,
  BulkEdge,
  CausalGraph,
  AmbiguityRegionData,
  visualizationResponseToCausalGraph,
} from "../types";
import { useHolographicData } from "../hooks/useHolographicData";
import { compareIncidents, IncidentComparisonResponse, NodeComparison } from "../api";

interface IncidentComparisonProps {
  incidentIdA: string;
  incidentIdB: string;
  className?: string;
}

interface ComparisonData {
  incidentId: string;
  data: VisualizationResponse | null;
  graph: CausalGraph | null;
  isLoading: boolean;
  error: string | null;
}

export function IncidentComparison({ incidentIdA, incidentIdB, className = "" }: IncidentComparisonProps) {
  // Fetch data for both incidents
  const dataA = useHolographicData({ incidentId: incidentIdA, autoFetch: true });
  const dataB = useHolographicData({ incidentId: incidentIdB, autoFetch: true });

  const [synchronized, setSynchronized] = useState(true);
  const [showDiff, setShowDiff] = useState(false);
  const [timeSync, setTimeSync] = useState(0);
  const [selectedNode, setSelectedNode] = useState<{ incidentId: string; nodeId: string } | null>(null);
  const [comparisonResult, setComparisonResult] = useState<IncidentComparisonResponse | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);

  // Leader camera for "Synchronize Camera": the first panel's camera is the
  // pose source; with sync on, the trailing panel copies it each frame.
  // (The toggle used to be wired to a no-op useFrame — "each canvas manages
  // its own camera" — so it did nothing.)
  const leaderCameraRef = useRef<THREE.Camera | null>(null);

  const comparisonData: [ComparisonData, ComparisonData] = useMemo(() => [
    {
      incidentId: incidentIdA,
      data: dataA.data,
      graph: dataA.causalGraph,
      isLoading: dataA.isLoading,
      error: dataA.error,
    },
    {
      incidentId: incidentIdB,
      data: dataB.data,
      graph: dataB.causalGraph,
      isLoading: dataB.isLoading,
      error: dataB.error,
    },
  ], [dataA, dataB]);

  // Fetch comparison from backend API. The effect aborts its in-flight
  // request on cleanup so a rapid incident switch can't deliver the stale
  // pair's comparison over the new one's.
  useEffect(() => {
    if (!dataA.data || !dataB.data) return;

    const controller = new AbortController();
    const fetchComparison = async () => {
      setComparisonLoading(true);
      try {
        const result = await compareIncidents(
          {
            incident_id_a: incidentIdA,
            incident_id_b: incidentIdB,
          },
          { signal: controller.signal }
        );
        if (!controller.signal.aborted) setComparisonResult(result);
      } catch (err) {
        if (!controller.signal.aborted) console.error("Failed to fetch comparison:", err);
      } finally {
        if (!controller.signal.aborted) setComparisonLoading(false);
      }
    };

    fetchComparison();
    return () => controller.abort();
  }, [incidentIdA, incidentIdB, dataA.data, dataB.data]);

  // Compute differences from API result or fallback to client-side
  const diffData = useMemo(() => {
    if (comparisonResult) {
      return {
        nodeDiffs: comparisonResult.node_comparisons.map(c => ({
          id: c.node_id,
          inA: c.in_a,
          inB: c.in_b,
          cpuDiff: c.cpu_delta,
          memoryDiff: c.memory_delta,
          errorDiff: c.error_rate_delta,
          latencyDiff: c.latency_delta,
          healthDiff: c.health_delta,
          metrics_a: c.metrics_a,
          metrics_b: c.metrics_b,
        })),
        summary: comparisonResult.summary,
      };
    }

    // Fallback to client-side computation
    if (!dataA.data || !dataB.data) return null;

    const nodesA = new Map(dataA.data.bulk_nodes.map(n => [n.id, n]));
    const nodesB = new Map(dataB.data.bulk_nodes.map(n => [n.id, n]));
    const allNodeIds = new Set([...nodesA.keys(), ...nodesB.keys()]);

    const nodeDiffs: Array<any> = [];

    for (const id of allNodeIds) {
      const nA = nodesA.get(id);
      const nB = nodesB.get(id);

      if (nA && nB) {
        const cpuA = nA.metrics?.cpu_usage || 0;
        const cpuB = nB.metrics?.cpu_usage || 0;
        const memA = nA.metrics?.memory_usage || 0;
        const memB = nB.metrics?.memory_usage || 0;
        const errA = nA.metrics?.error_rate || 0;
        const errB = nB.metrics?.error_rate || 0;
        const latA = nA.metrics?.latency_p99_ms || 0;
        const latB = nB.metrics?.latency_p99_ms || 0;

        const healthA = Math.max(0, 1 - Math.max(cpuA * 0.4, memA * 0.3, errA * 0.3));
        const healthB = Math.max(0, 1 - Math.max(cpuB * 0.4, memB * 0.3, errB * 0.3));

        nodeDiffs.push({
          id,
          inA: true,
          inB: true,
          cpuDiff: cpuB - cpuA,
          memoryDiff: memB - memA,
          errorDiff: errB - errA,
          latencyDiff: latB - latA,
          healthDiff: healthB - healthA,
        });
      } else if (nA) {
        nodeDiffs.push({ id, inA: true, inB: false, cpuDiff: 0, memoryDiff: 0, errorDiff: 0, latencyDiff: 0, healthDiff: 0 });
      } else if (nB) {
        nodeDiffs.push({ id, inA: false, inB: true, cpuDiff: 0, memoryDiff: 0, errorDiff: 0, latencyDiff: 0, healthDiff: 0 });
      }
    }

    return { nodeDiffs };
  }, [comparisonResult, dataA.data, dataB.data]);

  const handleNodeClick = useCallback((incidentId: string, nodeId: string) => {
    setSelectedNode({ incidentId, nodeId });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedNode(null);
  }, []);

  if (comparisonData[0].isLoading && comparisonData[1].isLoading) {
    return (
      <div className={`incident-comparison ${className}`}>
        <div className="comparison-loading">
          <div className="spinner"></div>
          <p>Loading holographic reconstructions...</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`incident-comparison ${className}`}>
      <div className="comparison-header">
        <h2>Incident Comparison</h2>
        <div className="comparison-controls">
          <label className="control-toggle">
            <input
              type="checkbox"
              checked={synchronized}
              onChange={(e) => setSynchronized(e.target.checked)}
            />
            <span>Synchronize Camera</span>
          </label>
          <label className="control-toggle">
            <input
              type="checkbox"
              checked={showDiff}
              onChange={(e) => setShowDiff(e.target.checked)}
              disabled={!diffData}
            />
            <span>Show Differences</span>
          </label>
          <label className="control-toggle">
            <input
              type="checkbox"
              checked={timeSync > 0}
              onChange={(e) => setTimeSync(e.target.checked ? 1 : 0)}
            />
            <span>Synchronize Time</span>
          </label>
        </div>
      </div>

      <div className="comparison-grid">
        {comparisonData.map((comp, index) => (
          <div key={comp.incidentId} className="comparison-panel">
            <div className="panel-header">
              <h3>{comp.incidentId}</h3>
              <div className="panel-status">
                {comp.isLoading && <span className="status loading">Loading...</span>}
                {comp.error && <span className="status error">{comp.error}</span>}
                {comp.data && !comp.isLoading && !comp.error && <span className="status ready">Ready</span>}
              </div>
            </div>
            <div className="panel-canvas">
              {comp.data && comp.graph && (
                <ComparisonCanvas
                  data={comp.data}
                  graph={comp.graph}
                  incidentId={comp.incidentId}
                  showDiff={showDiff}
                  diffData={diffData}
                  synchronizedCamera={synchronized}
                  onNodeClick={(nodeId) => handleNodeClick(comp.incidentId, nodeId)}
                  selectedNode={selectedNode?.incidentId === comp.incidentId ? selectedNode.nodeId : null}
                  isLeader={index === 0}
                  leaderCameraRef={leaderCameraRef}
                />
              )}
            </div>
            <div className="panel-metrics">
              {comp.data && (
                <IncidentMetricsSummary data={comp.data} diffData={diffData} incidentId={comp.incidentId} />
              )}
            </div>
          </div>
        ))}
      </div>

      {selectedNode && diffData && (
        <NodeDetailPanel
          nodeId={selectedNode.nodeId}
          incidentId={selectedNode.incidentId}
          diffData={diffData}
          onClose={clearSelection}
        />
      )}
    </div>
  );
}

/**
 * Individual canvas for one incident's holographic visualization
 */
interface ComparisonCanvasProps {
  data: VisualizationResponse;
  graph: CausalGraph;
  incidentId: string;
  showDiff: boolean;
  diffData: { nodeDiffs: any[] } | null;
  synchronizedCamera: boolean;
  onNodeClick: (nodeId: string) => void;
  selectedNode: string | null;
  isLeader: boolean;
  leaderCameraRef: React.MutableRefObject<THREE.Camera | null>;
}

function ComparisonCanvas({
  data,
  graph,
  showDiff,
  diffData,
  synchronizedCamera,
  onNodeClick,
  selectedNode,
  isLeader,
  leaderCameraRef,
}: ComparisonCanvasProps) {
  return (
    <div className="comparison-canvas-container">
      <Canvas
        camera={{ position: [0, 0, 50], fov: 45 }}
        style={{ width: "100%", height: "100%" }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[10, 10, 10]} intensity={1} />
        <CameraSync isLeader={isLeader} leaderCameraRef={leaderCameraRef} active={synchronizedCamera} />
        {/* While synchronized, the trailing panel locks to the leader:
            dragging both sides of a view you're meant to compare would
            fight the per-frame pose copy. */}
        <OrbitControls enabled={!synchronizedCamera || isLeader} />
        <HolographicScene
          data={data}
          graph={graph}
          showDiff={showDiff}
          diffData={diffData}
          onNodeClick={onNodeClick}
          selectedNode={selectedNode}
        />
      </Canvas>
    </div>
  );
}

/**
 * Publishes the leader panel's camera and, when active, keeps the trailing
 * panel's camera pose-locked to it.
 */
function CameraSync({
  isLeader,
  leaderCameraRef,
  active,
}: {
  isLeader: boolean;
  leaderCameraRef: React.MutableRefObject<THREE.Camera | null>;
  active: boolean;
}) {
  const { camera } = useThree();

  useEffect(() => {
    if (!isLeader) return;
    leaderCameraRef.current = camera;
    return () => {
      if (leaderCameraRef.current === camera) {
        leaderCameraRef.current = null;
      }
    };
  }, [camera, isLeader, leaderCameraRef]);

  useFrame(() => {
    if (!active || isLeader) return;
    const leader = leaderCameraRef.current;
    if (!leader || leader === camera) return;
    camera.position.copy(leader.position);
    camera.quaternion.copy(leader.quaternion);
  });

  return null;
}

/**
 * 3D Scene rendering the holographic reconstruction
 */
interface HolographicSceneProps {
  data: VisualizationResponse;
  graph: CausalGraph;
  showDiff: boolean;
  diffData: { nodeDiffs: any[] } | null;
  onNodeClick: (nodeId: string) => void;
  selectedNode: string | null;
}

function HolographicScene({ data, graph, showDiff, diffData, onNodeClick, selectedNode }: HolographicSceneProps) {
  const diffMap = useMemo(() => {
    if (!diffData) return new Map();
    const map = new Map();
    diffData.nodeDiffs.forEach(d => map.set(d.id, d));
    return map;
  }, [diffData]);

  // Region → node-position lookup: ambiguity regions name a component, they
  // carry no absolute position of their own.
  const nodePositions = useMemo(
    () => new Map(data.bulk_nodes.map((n) => [n.id, n.position])),
    [data.bulk_nodes]
  );

  return (
    <>
      {/* Render bulk nodes */}
      {data.bulk_nodes.map((node) => {
        const diff = diffMap.get(node.id);
        const isSelected = selectedNode === node.id;
        const inBoth = diff?.inA && diff?.inB;
        const onlyInA = diff?.inA && !diff?.inB;
        const onlyInB = diff?.inB && !diff?.inA;

        let color = new THREE.Color(0x4488ff);
        if (showDiff && diff) {
          if (!inBoth) {
            color = new THREE.Color(onlyInA ? 0xff4444 : 0x44ff44); // Red if only in A, green if only in B
          } else if (diff.healthDiff < -0.1) {
            color = new THREE.Color(0xff8800); // Orange for degraded
          } else if (diff.healthDiff > 0.1) {
            color = new THREE.Color(0x00ff88); // Green for improved
          }
        }

        const pos = node.position || [0, 0, 0];
        const scale = node.size || 1;

        return (
          <BulkNodeMesh
            key={node.id}
            nodeId={node.id}
            position={pos}
            scale={scale}
            color={color}
            isSelected={isSelected}
            onClick={onNodeClick}
            diff={diff}
            showDiff={showDiff}
          />
        );
      })}

      {/* Render edges */}
      {data.bulk_edges.map((edge) => (
        <BulkEdgeLine
          key={`${edge.source}-${edge.target}`}
          source={edge.source}
          target={edge.target}
          nodes={data.bulk_nodes}
          strength={edge.thickness || 1}
        />
      ))}

      {/* Ambiguity regions */}
      {data.ambiguity_regions.map((region, idx) => (
        <AmbiguityRegionMesh
          key={idx}
          region={region}
          position={nodePositions.get(region.component)}
        />
      ))}
    </>
  );
}

/**
 * Individual node mesh
 */
interface BulkNodeMeshProps {
  nodeId: string;
  position: [number, number, number];
  scale: number;
  color: THREE.Color;
  isSelected: boolean;
  onClick: (nodeId: string) => void;
  diff: any;
  showDiff: boolean;
}

function BulkNodeMesh({ nodeId, position, scale, color, isSelected, onClick, diff, showDiff }: BulkNodeMeshProps) {
  const meshRef = React.useRef<THREE.Mesh>(null);
  const [hovered, setHovered] = useState(false);

  return (
    <mesh
      ref={meshRef}
      position={position}
      scale={scale * (isSelected || hovered ? 1.2 : 1)}
      onPointerOver={() => setHovered(true)}
      onPointerOut={() => setHovered(false)}
      onClick={() => onClick(nodeId)}
    >
      <sphereGeometry args={[1, 32, 32]} />
      <meshStandardMaterial
        color={color}
        emissive={isSelected ? new THREE.Color(0xffff00) : color}
        emissiveIntensity={isSelected ? 0.5 : hovered ? 0.2 : 0}
        transparent
        opacity={showDiff && diff && !diff.inA && diff.inB ? 0.5 : showDiff && diff && diff.inA && !diff.inB ? 0.3 : 1}
      />
    </mesh>
  );
}

/**
 * Edge line between nodes
 */
interface BulkEdgeLineProps {
  source: string;
  target: string;
  nodes: any[];
  strength: number;
}

function BulkEdgeLine({ source, target, nodes, strength }: BulkEdgeLineProps) {
  const nodeMap = useMemo(() => new Map(nodes.map(n => [n.id, n.position])), [nodes]);
  const sourcePos = nodeMap.get(source);
  const targetPos = nodeMap.get(target);

  if (!sourcePos || !targetPos) return null;

  const points = [
    new THREE.Vector3(...sourcePos),
    new THREE.Vector3(...targetPos),
  ];

  const geometry = new THREE.BufferGeometry();
    geometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(points.flatMap(p => p.toArray()), 3)
    );

    return (
      <line>
        <primitive object={geometry} />
        <lineBasicMaterial
          color={0x888888}
          transparent
          opacity={0.5 * strength}
          linewidth={Math.max(1, strength * 3)}
        />
      </line>
    );
}

/**
 * Ambiguity region visualization
 */
interface AmbiguityRegionMeshProps {
  region: AmbiguityRegionData;
  /**
   * Position of the region's component node, resolved by HolographicScene.
   * Undefined when the component isn't part of this incident's nodes.
   */
  position?: [number, number, number];
}

function AmbiguityRegionMesh({ region, position }: AmbiguityRegionMeshProps) {
  // The old implementation read `region.center`/`region.radius`, which don't
  // exist on AmbiguityRegionData — every region fell back to the same
  // unit-size sphere at the origin, stacking all shells at [0,0,0]. Anchor
  // to the component instead; skip components with no node in this incident.
  if (!position) return null;

  const ambiguity = region.ambiguity_score || 0.5;
  const radius = 5 + ambiguity * 15;
  const severityColors: Partial<Record<AmbiguityRegionData["severity"], string>> = {
    low: "#f59e0b",
    medium: "#f97316",
    high: "#ef4444",
  };

  return (
    <mesh position={position}>
      <sphereGeometry args={[radius, 16, 16]} />
      <meshBasicMaterial
        color={severityColors[region.severity] ?? "#ff8800"}
        transparent
        opacity={Math.min(0.6, 0.15 + ambiguity * 0.3)}
        wireframe
      />
    </mesh>
  );
}

/**
 * Metrics summary panel for each incident
 */
interface IncidentMetricsSummaryProps {
  data: VisualizationResponse;
  diffData: { nodeDiffs: any[] } | null;
  incidentId: string;
}

function IncidentMetricsSummary({ data, diffData, incidentId }: IncidentMetricsSummaryProps) {
  const metrics = useMemo(() => {
    const nodes = data.bulk_nodes;
    if (nodes.length === 0) return null;

    let totalCpu = 0, totalMem = 0, totalErr = 0, totalLat = 0;
    let count = 0;

    nodes.forEach(n => {
      totalCpu += n.metrics?.cpu_usage || 0;
      totalMem += n.metrics?.memory_usage || 0;
      totalErr += n.metrics?.error_rate || 0;
      totalLat += n.metrics?.latency_p99_ms || 0;
      count++;
    });

    return {
      avgCpu: totalCpu / count,
      avgMem: totalMem / count,
      avgErr: totalErr / count,
      avgLat: totalLat / count,
      nodeCount: count,
      edgeCount: data.bulk_edges.length,
      anomalyCount: data.anomalies?.length || 0,
      ambiguityCount: data.ambiguity_regions?.length || 0,
    };
  }, [data]);

  const diffMap = useMemo(() => {
    if (!diffData) return null;
    const map = new Map();
    diffData.nodeDiffs.forEach(d => map.set(d.id, d));
    return map;
  }, [diffData]);

  if (!metrics) return <div className="metrics-empty">No data</div>;

  return (
    <div className="metrics-summary">
      <div className="metric-row">
        <span className="metric-label">Nodes:</span>
        <span className="metric-value">{metrics.nodeCount}</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Edges:</span>
        <span className="metric-value">{metrics.edgeCount}</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Avg CPU:</span>
        <span className="metric-value">{(metrics.avgCpu * 100).toFixed(1)}%</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Avg Memory:</span>
        <span className="metric-value">{(metrics.avgMem * 100).toFixed(1)}%</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Avg Error Rate:</span>
        <span className="metric-value">{(metrics.avgErr * 100).toFixed(2)}%</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Avg Latency:</span>
        <span className="metric-value">{metrics.avgLat.toFixed(1)}ms</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Anomalies:</span>
        <span className="metric-value">{metrics.anomalyCount}</span>
      </div>
      <div className="metric-row">
        <span className="metric-label">Ambiguity Regions:</span>
        <span className="metric-value">{metrics.ambiguityCount}</span>
      </div>
    </div>
  );
}

/**
 * Detail panel for selected node showing diff
 */
interface NodeDetailPanelProps {
  nodeId: string;
  incidentId: string;
  diffData: { nodeDiffs: any[] };
  onClose: () => void;
}

function NodeDetailPanel({ nodeId, incidentId, diffData, onClose }: NodeDetailPanelProps) {
  const diff = diffData.nodeDiffs.find(d => d.id === nodeId);

  if (!diff) return null;

  return (
    <div className="node-detail-panel">
      <div className="detail-header">
        <h4>Node Details: {nodeId}</h4>
        <button onClick={onClose} className="close-btn">×</button>
      </div>
      <div className="detail-content">
        <div className="detail-section">
          <h5>Comparison (A → B)</h5>
          <div className="diff-item">
            <span>CPU Usage:</span>
            <span className={diff.cpuDiff > 0 ? "worse" : diff.cpuDiff < 0 ? "better" : "neutral"}>
              {diff.cpuDiff > 0 ? "+" : ""}{(diff.cpuDiff * 100).toFixed(1)}%
            </span>
          </div>
          <div className="diff-item">
            <span>Memory Usage:</span>
            <span className={diff.memoryDiff > 0 ? "worse" : diff.memoryDiff < 0 ? "better" : "neutral"}>
              {diff.memoryDiff > 0 ? "+" : ""}{(diff.memoryDiff * 100).toFixed(1)}%
            </span>
          </div>
          <div className="diff-item">
            <span>Error Rate:</span>
            <span className={diff.errorDiff > 0 ? "worse" : diff.errorDiff < 0 ? "better" : "neutral"}>
              {diff.errorDiff > 0 ? "+" : ""}{(diff.errorDiff * 100).toFixed(2)}%
            </span>
          </div>
          <div className="diff-item">
            <span>Latency (p99):</span>
            <span className={diff.latencyDiff > 0 ? "worse" : diff.latencyDiff < 0 ? "better" : "neutral"}>
              {diff.latencyDiff > 0 ? "+" : ""}{diff.latencyDiff.toFixed(1)}ms
            </span>
          </div>
          <div className="diff-item health">
            <span>Health Delta:</span>
            <span className={diff.healthDiff > 0 ? "better" : diff.healthDiff < 0 ? "worse" : "neutral"}>
              {diff.healthDiff > 0 ? "+" : ""}{(diff.healthDiff * 100).toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="detail-section">
          <h5>Presence</h5>
          <p>In Incident A: {diff.inA ? "Yes" : "No"}</p>
          <p>In Incident B: {diff.inB ? "Yes" : "No"}</p>
        </div>
      </div>
    </div>
  );
}