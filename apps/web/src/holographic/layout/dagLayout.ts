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

  // Kahn processing order (parents before children) with PER-NODE depth
  // tracking: layer(v) = 1 + max{layer(u)}. A wave-counter would be plain
  // BFS layering — in graph A→B, A→C, B→C it puts C in wave 1 alongside B
  // even though C's longest causal chain is A→B→C (depth 2), collapsing
  // the two onto the same z-slab.
  const queue: string[] = [];
  const layers = new Map<string, number>();
  const depths = new Map<string, number>();

  inDegree.forEach((deg, id) => {
    if (deg === 0) {
      queue.push(id);
      depths.set(id, 0);
    }
  });

  let maxLayer = 0;
  while (queue.length > 0) {
    const id = queue.shift()!;
    const depth = depths.get(id) ?? 0;
    layers.set(id, depth);
    if (depth > maxLayer) maxLayer = depth;

    adj.get(id)?.forEach((neighbor) => {
      const newDeg = (inDegree.get(neighbor) || 0) - 1;
      inDegree.set(neighbor, newDeg);
      // Longest-path rule: neighbor can never be shallower than one past
      // its deepest processed parent.
      const candidate = depth + 1;
      if (candidate > (depths.get(neighbor) ?? 0)) depths.set(neighbor, candidate);
      if (newDeg === 0) queue.push(neighbor);
    });
  }

  // Fallback for cycles or unvisited nodes: place one slab past the deepest
  // layer real topology produced (cycle members have no valid depth).
  nodes.forEach((n) => {
    if (!layers.has(n.id)) {
      layers.set(n.id, maxLayer + 1);
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
