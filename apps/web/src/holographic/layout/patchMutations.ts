/**
 * Graph Mutation Model for Patches
 * Section 5.3 of Holographic Reconstruction Plan
 */

import { CausalGraph, GraphMutation } from "../types";

/**
 * Applies graph mutations to a causal graph to compute patched state
 */
export function applyPatch(graph: CausalGraph, mutations: GraphMutation[]): CausalGraph {
  const nextNodes = graph.nodes.map((n) => ({ ...n }));
  let nextLinks = graph.links.map((l) => ({ ...l }));

  for (const m of mutations) {
    switch (m.kind) {
      case "addNode":
        nextNodes.push({ ...m.node });
        break;
      case "removeNode":
        const idx = nextNodes.findIndex((n) => n.id === m.id);
        if (idx >= 0) nextNodes.splice(idx, 1);
        nextLinks = nextLinks.filter((l) => l.source !== m.id && l.target !== m.id);
        break;
      case "addEdge":
        nextLinks.push({ ...m.link });
        break;
      case "removeEdge":
        nextLinks = nextLinks.filter(
          (l) => !(l.source === m.source && l.target === m.target)
        );
        break;
      case "modifyEdge":
        const edge = nextLinks.find(
          (l) => l.source === m.source && l.target === m.target
        );
        if (edge) {
          edge.strength = m.after.strength;
        }
        break;
    }
  }

  return { nodes: nextNodes, links: nextLinks };
}
