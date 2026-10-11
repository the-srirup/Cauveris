/**
 * Hook for 3D Causal Graph Force-Directed Layout Simulation
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { CausalNode, CausalLink, ForceLayoutConfig } from "../types";
import { CausalForceSimulation, DEFAULT_FORCE_CONFIG } from "../layout/forceLayout";

export function useForceLayout(
  initialNodes: CausalNode[],
  initialLinks: CausalLink[],
  customConfig: Partial<ForceLayoutConfig> = {}
) {
  const [nodes, setNodes] = useState<CausalNode[]>(initialNodes);
  const [isConverged, setIsConverged] = useState(false);
  const simRef = useRef<CausalForceSimulation | null>(null);

  useEffect(() => {
    if (!initialNodes || initialNodes.length === 0) return;

    const sim = new CausalForceSimulation({
      ...DEFAULT_FORCE_CONFIG,
      ...customConfig,
    });
    simRef.current = sim;
    setIsConverged(false);

    sim.onTick((positions) => {
      // Build from the closure's initialNodes, NOT from `prev`: nodes usually
      // arrive from a fetch AFTER mount, so the useState(initialNodes)
      // snapshot is still [] and prev.map could never adopt the real nodes
      // (the layout stayed empty forever). The closure matches the same
      // effect run that seeded the simulation.
      setNodes(
        initialNodes.map((n) => {
          const pos = positions.get(n.id);
          if (!pos) return n;
          return {
            ...n,
            position: { x: pos.x, y: pos.y, z: pos.z },
            x: pos.x,
            y: pos.y,
            z: pos.z,
          };
        })
      );
    });

    sim.onConverged(() => {
      setIsConverged(true);
    });

    sim.init(initialNodes, initialLinks);

    return () => {
      sim.stop();
      // Drop the handle so `restart()` can't resurrect a torn-down
      // simulation (after unmount it would keep ticking and firing
      // setNodes on a dead component forever).
      if (simRef.current === sim) {
        simRef.current = null;
      }
    };
  }, [initialNodes, initialLinks]);

  const restart = useCallback(() => {
    simRef.current?.restart();
    setIsConverged(false);
  }, []);

  return {
    nodes,
    isConverged,
    restart,
  };
}
