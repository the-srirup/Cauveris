/**
 * DAG Layering and Topological Ordering for Causal Graphs
 * Section 1.4 & 3.1 of Holographic Reconstruction Plan
 */

import { CausalNode, CausalLink } from "../types";

/**
 * Computes topological layers via longest path:
 * layer(v) = 1 + max{layer(u)} for all u -> v
 */
export function computeTopologicalLayers(nodes: CausalNode[], links: CausalLink[]): Map<string, number> {
  const adj = new Map<string, Set<string>>();
  const inDegree = new Map<string, number>();

  nodes.forEach((n) => {
    adj.set(n.id, new Set());
    inDegree.set(n.id, 0);
  });

  links.forEach((l) => {
    const srcId = typeof l.source === "object" ? (l.source as any).id : l.source;
    const tgtId = typeof l.target === "object" ? (l.target as any).id : l.target;
    if (adj.has(srcId) && inDegree.has(tgtId)) {
      adj.get(srcId)?.add(tgtId);
      inDegree.set(tgtId, (inDegree.get(tgtId) || 0) + 1);
    }
  });

  const queue: string[] = [];
  const layers = new Map<string, number>();

  inDegree.forEach((deg, id) => {
    if (deg === 0) queue.push(id);
  });

  let currentLayer = 0;
  while (queue.length > 0) {
    const layerSize = queue.length;
    for (let i = 0; i < layerSize; i++) {
      const id = queue.shift()!;
      layers.set(id, currentLayer);
      adj.get(id)?.forEach((neighbor) => {
        const newDeg = (inDegree.get(neighbor) || 0) - 1;
        inDegree.set(neighbor, newDeg);
        if (newDeg === 0) queue.push(neighbor);
      });
    }
    currentLayer++;
  }

  // Fallback for cycles or unvisited nodes: place in final layer
  nodes.forEach((n) => {
    if (!layers.has(n.id)) {
      layers.set(n.id, currentLayer);
    }
  });

  return layers;
}

/**
 * Assigns Z-coordinate according to topological DAG layer:
 * z = (layer - centerOffset) * layerDistance
 * Freezes z in force simulation by fixing node.fz
 */
export function applyDAGLayering(
  nodes: CausalNode[],
  layers: Map<string, number>,
  layerDistance: number = 80
): CausalNode[] {
  let maxLayer = 0;
  layers.forEach((l) => {
    if (l > maxLayer) maxLayer = l;
  });

  const centerOffset = maxLayer / 2;

  nodes.forEach((node) => {
    const layer = layers.get(node.id) ?? 0;
    node.layer = layer;
    const zPos = (layer - centerOffset) * layerDistance;
    node.position.z = zPos;
    node.z = zPos;
    node.fz = zPos; // Fixed during XY force relaxation
  });

  return nodes;
}
