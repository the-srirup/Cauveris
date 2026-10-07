/**
 * 3D Causal Graph Rendering Component (React Three Fiber)
 * Section 3.1 & Day 7-8 of Holographic Reconstruction Plan
 */

import React, { useRef, useState, useMemo } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { CausalNode, CausalLink } from "../types";
import { getNodeColor, getLinkColor } from "../utils/colorPalettes";

interface NodeMeshProps {
  node: CausalNode;
  isSelected: boolean;
  isHovered: boolean;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

function NodeMesh({ node, isSelected, isHovered, onSelect, onHover }: NodeMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const color = useMemo(() => getNodeColor(node.type, node.health), [node.type, node.health]);

  useFrame((state) => {
    if (meshRef.current) {
      // Gentle floating animation
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.3;
      if (isSelected || isHovered) {
        const pulse = 1.0 + 0.15 * Math.sin(state.clock.elapsedTime * 4);
        meshRef.current.scale.setScalar(pulse);
      } else {
        meshRef.current.scale.setScalar(1.0);
      }
    }
  });

  return (
    <group position={[node.position.x, node.position.y, node.position.z]}>
      <mesh
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(node.id);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(node.id);
        }}
        onPointerOut={() => onHover(null)}
      >
        <sphereGeometry args={[node.radius || 10, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={
            isSelected
              ? new THREE.Color("#38bdf8")
              : isHovered
              ? new THREE.Color(color).multiplyScalar(0.4)
              : new THREE.Color(0x000000)
          }
          emissiveIntensity={isSelected ? 0.6 : 0.2}
          roughness={0.3}
          metalness={0.2}
        />
      </mesh>

      {/* Outer selection ring */}
      {isSelected && (
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[(node.radius || 10) * 1.3, (node.radius || 10) * 1.5, 32]} />
          <meshBasicMaterial color="#38bdf8" side={THREE.DoubleSide} transparent opacity={0.8} />
        </mesh>
      )}

      {/* Node label */}
      <Html
        distanceFactor={200}
        position={[0, (node.radius || 10) + 10, 0]}
        style={{
          pointerEvents: "none",
          transform: "translate3d(-50%, -50%, 0)",
          whiteSpace: "nowrap",
          userSelect: "none",
        }}
      >
        <div
          className={`px-2 py-0.5 rounded text-[11px] font-mono transition-all ${
            isSelected
              ? "bg-sky-500/90 text-white font-bold shadow-lg shadow-sky-500/50 scale-110"
              : isHovered
              ? "bg-slate-900/90 text-sky-300 border border-sky-400/50"
              : "bg-slate-950/70 text-slate-300 border border-slate-700/40 opacity-75"
          }`}
        >
          {node.label || node.name || node.id}
        </div>
      </Html>
    </group>
  );
}

interface LinkLineProps {
  link: CausalLink;
  nodesMap: Map<string, CausalNode>;
}

function LinkLine({ link, nodesMap }: LinkLineProps) {
  const srcId = typeof link.source === "object" ? (link.source as any).id : link.source;
  const tgtId = typeof link.target === "object" ? (link.target as any).id : link.target;
  const src = nodesMap.get(srcId);
  const tgt = nodesMap.get(tgtId);

  const lineObj = useMemo(() => {
    if (!src || !tgt) return null;

    const start = new THREE.Vector3(src.position.x, src.position.y, src.position.z);
    const end = new THREE.Vector3(tgt.position.x, tgt.position.y, tgt.position.z);

    const geom = new THREE.BufferGeometry().setFromPoints([start, end]);
    const linkColor = getLinkColor(link.strength, link.type);
    const mat = new THREE.LineBasicMaterial({
      color: linkColor,
      transparent: true,
      opacity: Math.max(0.3, Math.min(0.85, (link.strength || 0.5) + 0.2)),
      linewidth: 2,
    });

    return new THREE.Line(geom, mat);
  }, [src, tgt, link.strength, link.type]);

  if (!lineObj) return null;

  return <primitive object={lineObj} />;
}

export interface CausalGraph3DProps {
  nodes: CausalNode[];
  links: CausalLink[];
  selectedNodeId: string | null;
  onNodeSelect: (id: string | null) => void;
  onNodeHover?: (id: string | null) => void;
}

export function CausalGraph3D({
  nodes,
  links,
  selectedNodeId,
  onNodeSelect,
  onNodeHover,
}: CausalGraph3DProps) {
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const nodesMap = useMemo(() => {
    const map = new Map<string, CausalNode>();
    nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [nodes]);

  const handleHover = (id: string | null) => {
    setHoveredNodeId(id);
    onNodeHover?.(id);
  };

  return (
    <group>
      {/* Links */}
      {links.map((link, idx) => {
        const srcId = typeof link.source === "object" ? (link.source as any).id : link.source;
        const tgtId = typeof link.target === "object" ? (link.target as any).id : link.target;
        return (
          <LinkLine key={`link-${srcId}-${tgtId}-${idx}`} link={link} nodesMap={nodesMap} />
        );
      })}

      {/* Nodes */}
      {nodes.map((node) => (
        <NodeMesh
          key={node.id}
          node={node}
          isSelected={node.id === selectedNodeId}
          isHovered={node.id === hoveredNodeId}
          onSelect={(id) => onNodeSelect(id === selectedNodeId ? null : id)}
          onHover={handleHover}
        />
      ))}
    </group>
  );
}
