/**
 * 3D Causal Graph Rendering Component (React Three Fiber)
 * Section 3.1 & Day 7-8 of Holographic Reconstruction Plan
 */

import React, { useRef, useState, useMemo, useCallback } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { CausalNode, CausalLink } from "../types";
import { getNodeColor, getLinkColor } from "../utils/colorPalettes";

// Stable emissive instances — R3F copies these into material.emissive on
// prop updates (`emissive.set(value)`), so sharing them across nodes is
// safe; the alternative was allocating fresh THREE.Colors per node on
// every render.
const EMISSIVE_SELECTED = new THREE.Color("#38bdf8");
const EMISSIVE_NONE = new THREE.Color(0x000000);

interface NodeLabelSpriteProps {
  text: string;
  isSelected: boolean;
  isHovered: boolean;
  yOffset: number;
}

const NodeLabelSprite = React.memo(function NodeLabelSprite({
  text,
  isSelected,
  isHovered,
  yOffset,
}: NodeLabelSpriteProps) {
  const texture = useMemo(() => {
    if (typeof document === "undefined") return null;
    const canvas = document.createElement("canvas");
    canvas.width = 384;
    canvas.height = 72;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.clearRect(0, 0, 384, 72);

    const x = 8, y = 8, w = 368, h = 56, r = 12;
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);

    ctx.fillStyle = isSelected
      ? "rgba(24, 24, 27, 0.95)"
      : isHovered
      ? "rgba(15, 23, 42, 0.92)"
      : "rgba(2, 6, 23, 0.75)";
    ctx.fill();

    ctx.lineWidth = isSelected ? 3 : 2;
    ctx.strokeStyle = isSelected
      ? "#38bdf8"
      : isHovered
      ? "#64748b"
      : "rgba(51, 65, 85, 0.5)";
    ctx.stroke();

    ctx.font = isSelected ? "bold 24px monospace" : "20px monospace";
    ctx.fillStyle = isSelected ? "#38bdf8" : isHovered ? "#f1f5f9" : "#cbd5e1";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    let display = text;
    if (display.length > 24) {
      display = display.slice(0, 22) + "…";
    }
    ctx.fillText(display, 192, 36);

    const tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.needsUpdate = true;
    return tex;
  }, [text, isSelected, isHovered]);

  if (!texture) return null;

  const scaleX = isSelected ? 22 : 18;
  const scaleY = isSelected ? 4.4 : 3.6;

  return (
    <sprite position={[0, yOffset, 0]} scale={[scaleX, scaleY, 1]}>
      <spriteMaterial map={texture} transparent depthTest={false} depthWrite={false} />
    </sprite>
  );
});

interface NodeMeshProps {
  node: CausalNode;
  isSelected: boolean;
  isHovered: boolean;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

const NodeMesh = React.memo(function NodeMesh({ node, isSelected, isHovered, onSelect, onHover }: NodeMeshProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const color = useMemo(() => getNodeColor(node.type, node.health), [node.type, node.health]);
  const hoverEmissive = useMemo(() => new THREE.Color(color).multiplyScalar(0.4), [color]);

  // Read-through for the frame loop: with React.memo this component skips
  // re-renders when hover moves elsewhere, and a memoized component's
  // useFrame closure would otherwise keep stale isSelected/isHovered.
  const visualStateRef = useRef({ isSelected, isHovered });
  visualStateRef.current = { isSelected, isHovered };

  useFrame((state) => {
    if (meshRef.current) {
      // Gentle floating animation
      meshRef.current.rotation.y = state.clock.elapsedTime * 0.3;
      const { isSelected: sel, isHovered: hov } = visualStateRef.current;
      if (sel || hov) {
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
          emissive={isSelected ? EMISSIVE_SELECTED : isHovered ? hoverEmissive : EMISSIVE_NONE}
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
      <NodeLabelSprite
        text={node.label || node.name || node.id}
        isSelected={isSelected}
        isHovered={isHovered}
        yOffset={(node.radius || 10) + 7}
      />
    </group>
  );
});

interface LinkLineProps {
  link: CausalLink;
  nodesMap: Map<string, CausalNode>;
}

// Hover transitions re-render the whole graph — memoizing LinkLine (with
// the stable callbacks below) keeps the N links out of those renders.
const LinkLine = React.memo(function LinkLine({ link, nodesMap }: LinkLineProps) {
  const srcId = typeof link.source === "object" ? (link.source as any).id : link.source;
  const tgtId = typeof link.target === "object" ? (link.target as any).id : link.target;
  const src = nodesMap.get(srcId);
  const tgt = nodesMap.get(tgtId);

  // Create the line keyed on stable ids + style — NOT on node-object identity,
  // which changes on every force-layout tick (the previous deps rebuilt the
  // geometry + material + Line for every link on every tick and never disposed
  // the old objects). Position changes are applied in place by the
  // useLayoutEffect below.
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
    });

    return new THREE.Line(geom, mat);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [srcId, tgtId, link.strength, link.type]);

  // Release the previous geometry/material when the line is recreated or the
  // component unmounts (R3F never auto-disposes <primitive> object swaps).
  useEffect(() => {
    return () => {
      if (lineObj) {
        lineObj.geometry.dispose();
        (lineObj.material as THREE.Material).dispose();
      }
    };
  }, [lineObj]);

  // Keep the line endpoints in sync with the (per-tick) layout positions by
  // mutating the existing position buffer — no per-tick allocation.
  useLayoutEffect(() => {
    if (!lineObj || !src || !tgt) return;
    const posAttr = lineObj.geometry.getAttribute("position") as THREE.BufferAttribute;
    if (!posAttr) return;
    posAttr.setXYZ(0, src.position.x, src.position.y, src.position.z);
    posAttr.setXYZ(1, tgt.position.x, tgt.position.y, tgt.position.z);
    posAttr.needsUpdate = true;
    // needsUpdate only re-uploads the buffer; it does NOT invalidate the
    // cached boundingSphere, which three computes once from the INITIAL
    // endpoints — without this, links get wrongly frustum-culled once the
    // layout moves away from its initial centroid. (2-point geometry: cheap.)
    lineObj.geometry.computeBoundingSphere();
  });

  if (!lineObj) return null;

  return <primitive object={lineObj} />;
});

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

  // Stable identities so the memoized NodeMesh/LinkLine actually skip
  // renders: the old inline `onSelect={(id) => ...}` lambda had a fresh
  // identity per node per render, defeating any memoization.
  const handleHover = useCallback(
    (id: string | null) => {
      setHoveredNodeId(id);
      onNodeHover?.(id);
    },
    [onNodeHover]
  );

  const handleSelect = useCallback(
    (id: string) => onNodeSelect(id === selectedNodeId ? null : id),
    [onNodeSelect, selectedNodeId]
  );

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
          onSelect={handleSelect}
          onHover={handleHover}
        />
      ))}
    </group>
  );
}
