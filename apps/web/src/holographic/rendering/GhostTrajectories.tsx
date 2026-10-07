/**
 * Ghost Trajectories & Counterfactual State Overlay (R3F)
 * Section 5.1 of Holographic Reconstruction Plan
 */

import React, { useRef, useMemo } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { CausalNode, CounterfactualResult } from "../types";

export interface GhostTrajectoriesProps {
  nodes: CausalNode[];
  counterfactual: CounterfactualResult | null;
  visible?: boolean;
}

export function GhostTrajectories({
  nodes,
  counterfactual,
  visible = true,
}: GhostTrajectoriesProps) {
  const groupRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (groupRef.current) {
      // Subtle hovering pulse
      const t = state.clock.elapsedTime;
      groupRef.current.position.y = Math.sin(t * 2) * 1.5;
    }
  });

  if (!visible || !counterfactual) return null;

  return (
    <group ref={groupRef}>
      {nodes.map((node) => {
        const ghostPos = counterfactual.ghostPositions[node.id];
        const attr = counterfactual.attribution[node.id] || 0;
        const delta = (counterfactual.counterfactualValues[node.id] ?? node.health) - node.health;

        if (!ghostPos || Math.abs(delta) < 0.005) return null;

        const isIntervened = node.id === counterfactual.interventionNode;
        const ghostColor = isIntervened
          ? "#ec4899"
          : delta > 0
          ? "#10b981"
          : "#ef4444";

        const startVec = new THREE.Vector3(node.position.x, node.position.y, node.position.z);
        const endVec = new THREE.Vector3(ghostPos.x, ghostPos.y, ghostPos.z);
        const lineGeom = new THREE.BufferGeometry().setFromPoints([startVec, endVec]);

        return (
          <group key={`ghost-${node.id}`}>
            {/* Ghost sphere */}
            <mesh position={[ghostPos.x, ghostPos.y, ghostPos.z]}>
              <sphereGeometry args={[(node.radius || 10) * 0.95, 20, 20]} />
              <meshStandardMaterial
                color={ghostColor}
                emissive={ghostColor}
                emissiveIntensity={0.6 + Math.min(1.0, attr * 0.4)}
                transparent
                opacity={0.45}
                depthWrite={false}
                blending={THREE.AdditiveBlending}
                roughness={0.2}
              />
            </mesh>

            {/* Trajectory line from factual to counterfactual */}
            <primitive
              object={
                new THREE.Line(
                  lineGeom,
                  new THREE.LineDashedMaterial({
                    color: ghostColor,
                    dashSize: 3,
                    gapSize: 2,
                    transparent: true,
                    opacity: 0.6,
                  })
                )
              }
            />

            {/* Ghost delta label */}
            <Html
              distanceFactor={180}
              position={[ghostPos.x, ghostPos.y + (node.radius || 10) + 12, ghostPos.z]}
              style={{
                pointerEvents: "none",
                transform: "translate3d(-50%, -50%, 0)",
                whiteSpace: "nowrap",
              }}
            >
              <div className="px-1.5 py-0.5 rounded bg-slate-900/90 border border-slate-700 text-[10px] font-mono text-white shadow-md flex items-center gap-1">
                <span>{isIntervened ? "do(X):" : "CF:"}</span>
                <span className={delta > 0 ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                  {delta > 0 ? "+" : ""}
                  {(delta * 100).toFixed(0)}%
                </span>
              </div>
            </Html>
          </group>
        );
      })}
    </group>
  );
}
