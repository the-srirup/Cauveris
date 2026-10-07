/**
 * Web Worker for off-thread 3D force-directed layout simulation
 * Section 3.1 of Holographic Reconstruction Plan
 */

import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from "d3-force-3d";
import { computeTopologicalLayers, applyDAGLayering } from "./dagLayout";

let simulation: any = null;

self.onmessage = (e: MessageEvent) => {
  const { type, nodes, links, config } = e.data;

  if (type === "INIT") {
    if (simulation) {
      simulation.stop();
    }

    const simNodes = nodes.map((n: any) => ({
      ...n,
      x: n.position?.x ?? 0,
      y: n.position?.y ?? 0,
      z: n.position?.z ?? 0,
    }));

    if (config?.dagMode === "zout") {
      const layers = computeTopologicalLayers(simNodes, links);
      applyDAGLayering(simNodes, layers, config.dagLevelDistance || 80);
    }

    try {
      simulation = forceSimulation(simNodes, 3)
        .force(
          "charge",
          forceManyBody()
            .strength(config?.manyBodyStrength ?? -400)
            .theta(config?.manyBodyTheta ?? 0.9)
        )
        .force(
          "link",
          forceLink(links)
            .id((d: any) => d.id)
            .distance(config?.linkDistance ?? 70)
        )
        .force("center", forceCenter(0, 0, 0))
        .force(
          "collide",
          forceCollide((d: any) => (d.radius || 10) + 6).iterations(
            config?.collisionIterations ?? 2
          )
        )
        .alphaDecay(config?.alphaDecay ?? 0.0228)
        .velocityDecay(config?.velocityDecay ?? 0.4)
        .alphaMin(config?.alphaMin ?? 0.001);

      simulation.on("tick", () => {
        const positions = simNodes.map((n: any) => ({
          id: n.id,
          x: n.x,
          y: n.y,
          z: n.z,
        }));
        self.postMessage({ type: "TICK", positions });

        if (simulation.alpha() < (config?.alphaMin ?? 0.001)) {
          self.postMessage({ type: "CONVERGED", positions });
        }
      });

      simulation.alpha(1).restart();
    } catch (err) {
      self.postMessage({ type: "ERROR", error: String(err) });
    }
  }

  if (type === "STOP") {
    if (simulation) {
      simulation.stop();
      simulation = null;
    }
  }
};
