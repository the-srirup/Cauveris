/**
 * Web Worker for off-thread 3D force-directed layout simulation
 * Section 3.1 of Holographic Reconstruction Plan
 */

import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from "d3-force-3d";
import { computeTopologicalLayers, applyDAGLayering } from "./dagLayout";

let simulation: any = null;

// Under lib.dom, `self` is typed as Window, whose postMessage signature takes
// (message, targetOrigin) — but this file runs in a Worker where the second
// argument is the transfer list. Assert the real worker contract once here.
const postToMain = self.postMessage.bind(self) as unknown as (
  message: unknown,
  transfer?: ArrayBuffer[]
) => void;

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
        // Pack positions into a Float32Array and transfer the buffer instead
        // of structured-cloning a per-node object array on every tick.
        const positions = new Float32Array(simNodes.length * 3);
        const ids: string[] = simNodes.map((n: any) => n.id);
        simNodes.forEach((n: any, i: number) => {
          positions[i * 3] = n.x;
          positions[i * 3 + 1] = n.y;
          positions[i * 3 + 2] = n.z;
        });

        const hasConverged = simulation.alpha() < (config?.alphaMin ?? 0.001);
        // Copy BEFORE the TICK transfer below detaches the first buffer.
        const finalPositions = hasConverged ? new Float32Array(positions) : null;

        postToMain({ type: "TICK", ids, positions }, [positions.buffer]);
        if (finalPositions) {
          postToMain(
            { type: "CONVERGED", ids, positions: finalPositions },
            [finalPositions.buffer]
          );
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
