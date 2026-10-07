"use client";

import { useRef, useEffect, useState, useMemo } from "react";
import * as THREE from "three";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { OrbitControls, Html, Stars } from "@react-three/drei";
import { tv } from "tailwind-variants";

const holographicStyles = tv({
  base: `
    relative w-full h-full min-h-[600px] rounded-2xl overflow-hidden
    bg-[radial-gradient(ellipse_at_center,_var(--color-surface-2)_0%,_transparent_70%)]
    border border-[var(--color-border)]
  `,
  variants: {
    mode: {
      normal: "",
      dark: "bg-[radial-gradient(ellipse_at_center,_var(--color-brand-primary)/5_0%,_transparent_70%)]",
    },
  },
});

interface NodeData {
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
}

interface EdgeData {
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
}

interface AmbiguityRegion {
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

interface HolographicData {
  incident_id: string;
  bulk_nodes: NodeData[];
  bulk_edges: EdgeData[];
  boundary_layers: Record<string, Record<string, any>>;
  scale_hierarchy: any[];
  ambiguity_regions: AmbiguityRegion[];
  counterfactual: any;
  anomalies: any[];
  metadata: Record<string, any>;
}

interface HolographicCanvasProps {
  data: HolographicData | null;
  selectedNode: string | null;
  onNodeSelect: (nodeId: string | null) => void;
  onNodeHover: (nodeId: string | null) => void;
  animationSpeed: number;
  showAmbiguity: boolean;
  showCounterfactual: boolean;
  quality: "low" | "medium" | "high";
  mode?: "normal" | "dark";
  className?: string;
}

const MAX_INSTANCES = 10000;

// Node Instanced Mesh Component
function BulkNodes({
  nodes,
  selectedId,
  hoveredId,
  onSelect,
  onHover,
  quality,
}: {
  nodes: NodeData[];
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  quality: "low" | "medium" | "high";
}) {
  const { camera } = useThree();
  const instancesRef = useRef<number>(nodes.length);
  const dummy = useRef(new THREE.Object3D());
  const meshRef = useRef<THREE.InstancedMesh | null>(null);

  // Geometry based on quality
  const geometry = useMemo(() => {
    const detail = quality === "high" ? 32 : quality === "medium" ? 16 : 8;
    return new THREE.IcosahedronGeometry(1, detail);
  }, [quality]);

  // Create instanced mesh
  useEffect(() => {
    const count = Math.min(nodes.length, MAX_INSTANCES);
    instancesRef.current = count;

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.9,
      flatShading: quality === "low",
    });

    const mesh = new THREE.InstancedMesh(geometry, material, count);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(count * 3), 3);
    meshRef.current = mesh;

    return () => {
      geometry.dispose();
      material.dispose();
      mesh.dispose();
    };
  }, [nodes.length, quality]);

  // Update instances per frame
  useFrame(() => {
    if (!meshRef.current || nodes.length === 0) return;

    const mesh = meshRef.current;
    if (!mesh.instanceColor) return;
    const matrix = dummy.current.matrix;
    const colors = mesh.instanceColor.array as Float32Array;

    for (let i = 0; i < instancesRef.current && i < nodes.length; i++) {
      const node = nodes[i];

      // Position
      dummy.current.position.set(...node.position);
      dummy.current.scale.setScalar(node.size);

      // Rotation (subtle animation for alive nodes)
      const time = performance.now() * 0.001;
      dummy.current.rotation.y = time * 0.1 + node.id.charCodeAt(0) * 0.1;

      dummy.current.updateMatrix();
      mesh.setMatrixAt(i, matrix);

      // Color with health pulsing
      const baseColor = new THREE.Color(node.color);
      const pulse = 1.0 + 0.1 * Math.sin(time * 2 + i);
      const r = Math.min(1, baseColor.r * pulse * node.health);
      const g = Math.min(1, baseColor.g * pulse * node.health);
      const b = Math.min(1, baseColor.b * pulse);

      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;

      // Highlight selected/hovered
      if (node.id === selectedId) {
        colors[i * 3] = 1.0;
        colors[i * 3 + 1] = 1.0;
        colors[i * 3 + 2] = 0.2;
      } else if (node.id === hoveredId) {
        colors[i * 3] = Math.min(1, colors[i * 3] * 1.5);
        colors[i * 3 + 1] = Math.min(1, colors[i * 3 + 1] * 1.5);
      }
    }

    mesh.instanceMatrix.needsUpdate = true;
    mesh.instanceColor.needsUpdate = true;
  });

  // Raycasting for selection
  const handlePointerMove = (event: THREE.Event) => {
    if (event.type === "pointermove") {
      const raycastEvent = event as any;
      const intersects = raycastEvent.intersections;
      if (intersects.length > 0) {
        const index = intersects[0].instanceId;
        if (index !== undefined && index < nodes.length) {
          onHover(nodes[index].id);
        } else {
          onHover(null);
        }
      } else {
        onHover(null);
      }
    }
  };

  const handleClick = (event: THREE.Event) => {
    const raycastEvent = event as any;
    const intersects = raycastEvent.intersections;
    if (intersects.length > 0) {
      const index = intersects[0].instanceId;
      if (index !== undefined && index < nodes.length) {
        onSelect(nodes[index].id);
      }
    }
  };

  return (
    <group>
      <instancedMesh
        ref={meshRef}
        args={[geometry, undefined, instancesRef.current]}
        onPointerMove={handlePointerMove}
        onClick={handleClick}
      />

      {/* Node labels - HTML overlay */}
      {nodes.slice(0, 50).map((node, i) => (
        <Html
          key={node.id}
          transform
          position={node.position}
          style={{
            pointerEvents: "none",
            fontSize: "10px",
            color: node.id === selectedId ? "var(--color-brand-primary)" : "var(--color-text-muted)",
            fontWeight: node.id === selectedId ? "bold" : "normal",
            textShadow: "0 0 4px var(--theme-background)",
            whiteSpace: "nowrap",
            opacity: node.id === selectedId || node.id === hoveredId ? 1 : 0.6,
            transition: "opacity 0.2s",
          }}
        >
          {node.name}
        </Html>
      ))}
    </group>
  );
}

// Edge Instanced Lines Component
function BulkEdges({
  edges,
  nodes,
  quality,
}: {
  edges: EdgeData[];
  nodes: NodeData[];
  quality: "low" | "medium" | "high";
}) {
  const edgeGeometry = useMemo(() => {
    // Pre-compute edge geometries
    return new THREE.BufferGeometry();
  }, []);

  // Create line segments using InstancedBufferGeometry for performance
  const positions = useMemo(() => {
    const nodeMap = new Map(nodes.map(n => [n.id, n.position]));
    const maxEdges = Math.min(edges.length, MAX_INSTANCES);
    const positions = new Float32Array(maxEdges * 6); // 2 points * 3 coords

    for (let i = 0; i < maxEdges; i++) {
      const edge = edges[i];
      const srcPos = nodeMap.get(edge.source);
      const dstPos = nodeMap.get(edge.target);

      if (srcPos && dstPos) {
        positions[i * 6] = srcPos[0];
        positions[i * 6 + 1] = srcPos[1];
        positions[i * 6 + 2] = srcPos[2];
        positions[i * 6 + 3] = dstPos[0];
        positions[i * 6 + 4] = dstPos[1];
        positions[i * 6 + 5] = dstPos[2];
      }
    }

    return positions;
  }, [edges, nodes]);

  const colors = useMemo(() => {
    const maxEdges = Math.min(edges.length, MAX_INSTANCES);
    const colors = new Float32Array(maxEdges * 6); // 2 points * 3 colors (same per edge)

    for (let i = 0; i < maxEdges; i++) {
      const edge = edges[i];
      const color = new THREE.Color(edge.color);

      // Source point color
      colors[i * 6] = color.r;
      colors[i * 6 + 1] = color.g;
      colors[i * 6 + 2] = color.b;

      // Target point color
      colors[i * 6 + 3] = color.r;
      colors[i * 6 + 4] = color.g;
      colors[i * 6 + 5] = color.b;
    }

    return colors;
  }, [edges]);

  const lineSegmentsObj = useMemo(() => {
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geom.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const mat = new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.6,
    });

    return new THREE.LineSegments(geom, mat);
  }, [positions, colors]);

  return <primitive object={lineSegmentsObj} />;
}

// Ambiguity Region Visualization
function AmbiguityRegions({
  regions,
  nodes,
  visible,
}: {
  regions: AmbiguityRegion[];
  nodes: NodeData[];
  visible: boolean;
}) {
  if (!visible || regions.length === 0) return null;

  const nodeMap = new Map(nodes.map(n => [n.id, n.position]));

  return (
    <group>
      {regions.map((region, i) => {
        const pos = nodeMap.get(region.component);
        if (!pos) return null;

        const severityColors = {
          low: "#f59e0b",
          medium: "#f97316",
          high: "#ef4444",
        };

        const color = severityColors[region.severity];
        const intensity = region.ambiguity_score;

        return (
          <group key={i}>
            <mesh position={pos}>
              <sphereGeometry args={[8 + intensity * 20, 16, 16]} />
              <meshBasicMaterial
                color={color}
                transparent
                opacity={0.15 + intensity * 0.2}
                side={THREE.DoubleSide}
              />
            </mesh>
            <mesh position={pos}>
              <ringGeometry args={[10 + intensity * 25, 12 + intensity * 30, 32]} />
              <meshBasicMaterial
                color={color}
                transparent
                opacity={0.3 + intensity * 0.3}
                side={THREE.DoubleSide}
              />
            </mesh>
            <Html
              transform
              position={[pos[0], pos[1] + 15 + intensity * 20, pos[2]]}
              style={{
                pointerEvents: "none",
                fontSize: "11px",
                color,
                fontWeight: "bold",
                textShadow: "0 0 4px var(--theme-background)",
                background: "var(--theme-background)/80",
                padding: "2px 6px",
                borderRadius: "4px",
                border: `1px solid ${color}`,
              }}
            >
              ⚠ {region.ambiguity_score.toFixed(0)}% Ambiguous
            </Html>
          </group>
        );
      })}
    </group>
  );
}

// Boundary Layer Heatmap Visualization
function BoundaryLayers({
  boundaryLayers,
  nodes,
  visible,
}: {
  boundaryLayers: Record<string, Record<string, any>>;
  nodes: NodeData[];
  visible: boolean;
}) {
  if (!visible) return null;

  const nodeMap = new Map(nodes.map(n => [n.id, n.position]));

  return (
    <group>
      {Object.entries(boundaryLayers).map(([compName, layers]) => {
        const pos = nodeMap.get(compName);
        if (!pos) return null;

        return (
          <group key={compName}>
            {Object.entries(layers).map(([layerName, layerData], i) => {
              const weight = layerData.reconstruction_weight || 0;
              const ambiguity = layerData.ambiguity_score || 0;
              const color = layerData.color || "#6b7280";

              return (
                <mesh
                  key={layerName}
                  position={[pos[0], pos[1] + 25 + i * 8, pos[2]]}>
                  <torusGeometry args={[4 + weight * 10, 1.5, 8, 16]} />
                  <meshBasicMaterial
                    color={color}
                    transparent
                    opacity={0.3 + weight * 0.4}
                    side={THREE.DoubleSide}
                  />
                </mesh>
              );
            })}
          </group>
        );
      })}
    </group>
  );
}

// Main Holographic Scene
function HolographicScene({
  data,
  selectedNode,
  onNodeSelect,
  onNodeHover,
  animationSpeed,
  showAmbiguity,
  showBoundaryLayers,
  quality,
}: HolographicCanvasProps & {
  showBoundaryLayers: boolean;
}) {
  const { scene } = useThree();
  const timeRef = useRef(0);

  // Background animation
  useFrame((state) => {
    timeRef.current = state.clock.getElapsedTime() * animationSpeed;

    // Subtle scene rotation
    scene.rotation.y = Math.sin(timeRef.current * 0.1) * 0.02;
  });

  // Camera position
  const [cameraPosition] = useState<[number, number, number]>([0, 50, 200]);

  return (
    <>
      {/* Ambient lighting */}
      <ambientLight intensity={0.5} color="#ffffff" />
      <directionalLight
        position={[100, 200, 100]}
        intensity={1.5}
        color="#ffffff"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-near={0.1}
        shadow-camera-far={500}
        shadow-camera-left={-200}
        shadow-camera-right={200}
        shadow-camera-top={200}
        shadow-camera-bottom={-200}
      />
      <directionalLight
        position={[-100, 100, -100]}
        intensity={0.5}
        color="#3b82f6"
      />
      <pointLight position={[0, 100, 0]} intensity={0.5} color="#8b5cf6" distance={400} decay={2} />

      {/* Stars background */}
      <Stars radius={500} depth={100} count={2000} factor={4} saturation={0} fade />

      {/* Grid floor */}
      <gridHelper args={[400, 40, "#334155", "#1e293b"]} position={[0, -50, 0]} />

      {/* Main visualization */}
      {data && (
        <>
          <BoundaryLayers
            boundaryLayers={data.boundary_layers}
            nodes={data.bulk_nodes}
            visible={showBoundaryLayers}
          />
          <BulkEdges
            edges={data.bulk_edges}
            nodes={data.bulk_nodes}
            quality={quality}
          />
          <BulkNodes
            nodes={data.bulk_nodes}
            selectedId={selectedNode}
            hoveredId={null} // handled by BulkNodes internally
            onSelect={onNodeSelect}
            onHover={onNodeHover}
            quality={quality}
          />
          <AmbiguityRegions
            regions={data.ambiguity_regions}
            nodes={data.bulk_nodes}
            visible={showAmbiguity}
          />
        </>
      )}
    </>
  );
}

export function HolographicCanvas({
  data,
  selectedNode,
  onNodeSelect,
  onNodeHover,
  animationSpeed = 1,
  showAmbiguity = true,
  showCounterfactual = false,
  quality = "high",
  mode = "normal",
  className = "",
}: HolographicCanvasProps) {
  const [showBoundaryLayers, setShowBoundaryLayers] = useState(true);

  return (
    <div className={`${holographicStyles({ mode })} ${className}`} style={{ position: "relative" }}>
      <Canvas
        camera={{ position: [0, 50, 200], fov: 50, near: 0.1, far: 1000 }}
        gl={{
          antialias: quality !== "low",
          alpha: true,
          powerPreference: "high-performance",
          stencil: false,
          depth: true,
          preserveDrawingBuffer: false,
        }}
        shadows={quality !== "low"}
        dpr={[1, 2]}
      >
        <HolographicScene
          data={data}
          selectedNode={selectedNode}
          onNodeSelect={onNodeSelect}
          onNodeHover={onNodeHover}
          animationSpeed={animationSpeed}
          showAmbiguity={showAmbiguity}
          showBoundaryLayers={showBoundaryLayers}
          showCounterfactual={showCounterfactual}
          quality={quality}
        />
        <OrbitControls
          enablePan={true}
          enableZoom={true}
          enableRotate={true}
          minDistance={50}
          maxDistance={500}
          minPolarAngle={0}
          maxPolarAngle={Math.PI / 2 - 0.01}
          dampingFactor={0.05}
        />
      </Canvas>

      {/* Controls overlay */}
      <div className="absolute bottom-4 left-4 right-4 md:left-auto md:right-4 md:bottom-4 md:w-auto flex flex-wrap gap-2">
        <button
          onClick={() => setShowBoundaryLayers(!showBoundaryLayers)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            showBoundaryLayers
              ? "bg-[var(--color-brand-primary)] text-white"
              : "bg-[var(--color-surface)] text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)]"
          }`}
        >
          {showBoundaryLayers ? "Hide Layers" : "Show Layers"}
        </button>
        <button
          onClick={() => {}}
          className="px-3 py-1.5 rounded-lg bg-[var(--color-surface)] text-[var(--color-text-muted)] text-xs font-medium hover:bg-[var(--color-surface-2)] transition-colors"
        >
          Reset View
        </button>
      </div>

      {/* Legend */}
      <div className="absolute top-4 right-4 p-3 rounded-lg bg-[var(--theme-background)]/90 backdrop-blur border border-[var(--color-border)] text-xs">
        <div className="font-semibold text-[var(--color-text-primary)] mb-2">Legend</div>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-green-500" />
            <span className="text-[var(--color-text-muted)]">Healthy</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-yellow-500" />
            <span className="text-[var(--color-text-muted)]">Degraded</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full bg-red-500" />
            <span className="text-[var(--color-text-muted)]">Critical</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded-full border-2 border-dashed border-amber-500" />
            <span className="text-[var(--color-text-muted)]">Ambiguous</span>
          </div>
        </div>
      </div>
    </div>
  );
}