/**
 * Patch Visualization as Graph Mutations
 * Section 5.3 of Holographic Reconstruction Plan
 */

import React, { useMemo } from "react";
import * as THREE from "three";
import { Html } from "@react-three/drei";
import { CausalGraph, GraphMutation } from "../types";
import { applyPatch } from "../layout/patchMutations";

export { applyPatch };

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
              <Html
                distanceFactor={160}
                position={[midX, midY + 10, midZ]}
                style={{
                  pointerEvents: "none",
                  transform: "translate3d(-50%, -50%, 0)",
                  whiteSpace: "nowrap",
                }}
              >
                <div className="px-2 py-0.5 rounded bg-amber-950/90 border border-amber-500/80 text-[10px] font-mono text-amber-300 shadow">
                  Patch: {delta > 0 ? "+" : ""}
                  {(delta * 100).toFixed(0)}% causal weight
                </div>
              </Html>
            </group>
          );
        }

        return null;
      })}
    </group>
  );
}
