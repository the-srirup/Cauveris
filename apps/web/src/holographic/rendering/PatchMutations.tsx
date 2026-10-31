/**
 * Patch Visualization as Graph Mutations
 * Section 5.3 of Holographic Reconstruction Plan
 */

import React, { useMemo } from "react";
import * as THREE from "three";
import { CausalGraph, GraphMutation } from "../types";
import { applyPatch } from "../layout/patchMutations";

export { applyPatch };

interface PatchLabelSpriteProps {
  delta: number;
  position: [number, number, number];
}

const PatchLabelSprite = React.memo(function PatchLabelSprite({
  delta,
  position,
}: PatchLabelSpriteProps) {
  const texture = useMemo(() => {
    if (typeof document === "undefined") return null;
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.clearRect(0, 0, 320, 64);
    const x = 6, y = 6, w = 308, h = 52, r = 8;
    ctx.beginPath();
    ctx.roundRect(x, y, w, h, r);
    ctx.fillStyle = "rgba(24, 24, 27, 0.95)";
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = "#52525b";
    ctx.stroke();

    ctx.font = "bold 18px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillStyle = "#e4e4e7";

    const label = `Patch: ${delta > 0 ? "+" : ""}${(delta * 100).toFixed(0)}% weight`;
    ctx.fillText(label, 160, 32);

    const tex = new THREE.CanvasTexture(canvas);
    tex.minFilter = THREE.LinearFilter;
    tex.generateMipmaps = false;
    tex.needsUpdate = true;
    return tex;
  }, [delta]);

  if (!texture) return null;

  return (
    <sprite position={position} scale={[18, 3.6, 1]}>
      <spriteMaterial map={texture} transparent depthTest={false} depthWrite={false} />
    </sprite>
  );
});

export interface PatchMutationsProps {
  mutations: GraphMutation[];
  nodes: CausalGraph["nodes"];
  visible?: boolean;
}

export function PatchMutations({ mutations, nodes, visible = true }: PatchMutationsProps) {
  const nodesMap = useMemo(() => {
    const map = new Map<string, (typeof nodes)[0]>();
    nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [nodes]);

  if (!visible || mutations.length === 0) return null;

  return (
    <group>
      {mutations.map((m, idx) => {
        if (m.kind === "addNode") {
          return (
            <mesh key={`patch-add-${idx}`} position={[m.node.position.x, m.node.position.y, m.node.position.z]}>
              <ringGeometry args={[(m.node.radius || 10) * 1.4, (m.node.radius || 10) * 1.6, 32]} />
              <meshBasicMaterial color="#10b981" side={THREE.DoubleSide} transparent opacity={0.8} />
            </mesh>
          );
        }

        if (m.kind === "removeNode") {
          const n = nodesMap.get(m.id);
          if (!n) return null;
          return (
            <mesh key={`patch-rem-${idx}`} position={[n.position.x, n.position.y, n.position.z]}>
              <ringGeometry args={[(n.radius || 10) * 1.4, (n.radius || 10) * 1.6, 32]} />
              <meshBasicMaterial color="#ef4444" side={THREE.DoubleSide} transparent opacity={0.8} />
            </mesh>
          );
        }

        if (m.kind === "modifyEdge") {
          const src = nodesMap.get(m.source);
          const tgt = nodesMap.get(m.target);
          if (!src || !tgt) return null;

          const midX = (src.position.x + tgt.position.x) / 2;
          const midY = (src.position.y + tgt.position.y) / 2;
          const midZ = (src.position.z + tgt.position.z) / 2;

          const delta = m.after.strength - m.before.strength;

          return (
            <group key={`patch-mod-${idx}`}>
              <PatchLabelSprite delta={delta} position={[midX, midY + 10, midZ]} />
            </group>
          );
        }

        return null;
      })}
    </group>
  );
}
