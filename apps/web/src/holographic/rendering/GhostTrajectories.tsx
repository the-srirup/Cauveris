/**
 * Ghost Trajectories & Counterfactual State Overlay (R3F)
 * Section 5.1 of Holographic Reconstruction Plan
 */

import React, { useRef, useMemo, useEffect } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { CausalNode, CounterfactualResult } from "../types";

export interface GhostTrajectoriesProps {
  nodes: CausalNode[];
  counterfactual: CounterfactualResult | null;
  visible?: boolean;
}

/**
 * A single factual→counterfactual trajectory line. Memoized on endpoint
 * *values* so a re-render during force layout does not rebuild (and leak)
 * geometry/material/Line per tick. Disposes its GPU resources on change and
 * unmount (R3F never auto-disposes <primitive> object swaps).
 */
function GhostLine({
  from,
  to,
  color,
}: {
  from: [number, number, number];
  to: [number, number, number];
  color: string;
}) {
  const lineObj = useMemo(() => {
    const start = new THREE.Vector3(from[0], from[1], from[2]);
    const end = new THREE.Vector3(to[0], to[1], to[2]);
    const geom = new THREE.BufferGeometry().setFromPoints([start, end]);
    const mat = new THREE.LineDashedMaterial({
      color,
      dashSize: 3,
      gapSize: 2,
      transparent: true,
      opacity: 0.6,
    });
    const line = new THREE.Line(geom, mat);
    // Without computeLineDistances() LineDashedMaterial renders as a solid line.
    line.computeLineDistances();
    return line;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [from[0], from[1], from[2], to[0], to[1], to[2], color]);

  useEffect(() => {
    return () => {
      lineObj.geometry.dispose();
      (lineObj.material as THREE.Material).dispose();
    };
  }, [lineObj]);

  return <primitive object={lineObj} />;
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
            <GhostLine
              from={[node.position.x, node.position.y, node.position.z]}
              to={[ghostPos.x, ghostPos.y, ghostPos.z]}
              color={ghostColor}
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
                <span className={delta > 0 ? "text-zinc-200 font-bold" : "text-zinc-400 font-bold"}>
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
