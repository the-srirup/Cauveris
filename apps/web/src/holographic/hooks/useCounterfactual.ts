/**
 * Pearl's 3-Step Counterfactual Simulation Hook
 * Section 5.1 of Holographic Reconstruction Plan
 */

import { useState, useCallback, useMemo } from "react";
import { CausalNode, CausalLink, CounterfactualResult, NodeDiff, Vec3 } from "../types";
import { computeTopologicalLayers } from "../layout/dagLayout";

export function useCounterfactual(nodes: CausalNode[], links: CausalLink[]) {
  const [result, setResult] = useState<CounterfactualResult | null>(null);
  const [isComputing, setIsComputing] = useState(false);

  const topoOrder = useMemo(() => {
    const layers = computeTopologicalLayers(nodes, links);
    const sorted = [...nodes].sort((a, b) => (layers.get(a.id) ?? 0) - (layers.get(b.id) ?? 0));
    return sorted.map((n) => n.id);
  }, [nodes, links]);

  const parentsMap = useMemo(() => {
    const map = new Map<string, string[]>();
    nodes.forEach((n) => map.set(n.id, []));
    links.forEach((l) => {
      const src = typeof l.source === "object" ? (l.source as any).id : l.source;
      const tgt = typeof l.target === "object" ? (l.target as any).id : l.target;
      if (map.has(tgt)) {
        map.get(tgt)!.push(src);
      }
    });
    return map;
  }, [nodes, links]);

  const intervene = useCallback(
    async (interventionNodeId: string, interventionHealthValue: number) => {
      setIsComputing(true);

      try {
        const nodeMap = new Map<string, CausalNode>();
        nodes.forEach((n) => nodeMap.set(n.id, n));

        // Step 1: Abduction - estimate noise epsilon_i
        const noiseMap = new Map<string, number>();
        for (const id of topoOrder) {
          const node = nodeMap.get(id);
          if (!node) continue;

          const parents = parentsMap.get(id) || [];
          let deterministic = 0;
          if (parents.length > 0) {
            let sum = 0;
            for (const pid of parents) {
              const p = nodeMap.get(pid);
              if (p) sum += p.health;
            }
            deterministic = sum / parents.length;
          }

          const noise = node.health - deterministic;
          noiseMap.set(id, noise);
        }

        // Step 2 & 3: Action & Prediction
        const counterfactualValues: Record<string, number> = {};
        const factualValues: Record<string, number> = {};
        for (const n of nodes) {
          factualValues[n.id] = n.health;
          counterfactualValues[n.id] = n.health;
        }

        // do(X = x')
        counterfactualValues[interventionNodeId] = interventionHealthValue;

        for (const id of topoOrder) {
          if (id === interventionNodeId) continue; // Severed: set by action

          const parents = parentsMap.get(id) || [];
          let deterministic = 0;
          if (parents.length > 0) {
            let sum = 0;
            for (const pid of parents) {
              sum += counterfactualValues[pid] ?? 0;
            }
            deterministic = sum / parents.length;
          }

          const noise = noiseMap.get(id) ?? 0;
          const predicted = Math.max(0, Math.min(1, deterministic + noise));
          counterfactualValues[id] = predicted;
        }

        // Compute attribution & ghost positions
        const attribution: Record<string, number> = {};
        const ghostPositions: Record<string, Vec3> = {};
        const diff: NodeDiff[] = [];

        for (const node of nodes) {
          const delta = counterfactualValues[node.id] - factualValues[node.id];
          const attr = Math.abs(delta) / 0.2; // normalized by standard deviation proxy
          attribution[node.id] = attr;

          // Ghost layout position bias: displace slightly along Y and Z based on delta
          const scale = 20;
          ghostPositions[node.id] = {
            x: node.position.x + Math.sin(node.position.x) * 4,
            y: node.position.y + delta * scale,
            z: node.position.z + (Math.abs(delta) > 0.05 ? 15 : 0),
          };

          diff.push({
            nodeId: node.id,
            positionDelta: {
              x: ghostPositions[node.id].x - node.position.x,
              y: ghostPositions[node.id].y - node.position.y,
              z: ghostPositions[node.id].z - node.position.z,
            },
            valueDelta: delta,
            attribution: attr,
            type: Math.abs(delta) > 0.01 ? "modified" : "unchanged",
          });
        }

        setResult({
          interventionNode: interventionNodeId,
          interventionValue: interventionHealthValue,
          factualValues,
          counterfactualValues,
          attribution,
          ghostPositions,
          diff,
        });
      } finally {
        setIsComputing(false);
      }
    },
    [nodes, topoOrder, parentsMap]
  );

  const reset = useCallback(() => {
    setResult(null);
  }, []);

  return {
    result,
    isComputing,
    intervene,
    reset,
  };
}
