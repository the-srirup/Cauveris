/**
 * 3D Force-Directed Layout Engine using d3-force-3d
 * Section 1.4 & 3.1 of Holographic Reconstruction Plan
 */

import { forceSimulation, forceManyBody, forceLink, forceCenter, forceCollide } from "d3-force-3d";
import { CausalNode, CausalLink, ForceLayoutConfig } from "../types";
import { computeTopologicalLayers, applyDAGLayering } from "./dagLayout";

export const DEFAULT_FORCE_CONFIG: ForceLayoutConfig = {
  // Barnes-Hut many-body force
  manyBodyStrength: -400,
  manyBodyTheta: 0.9,
  manyBodyDistanceMin: 10,
  manyBodyDistanceMax: 600,

  // Link spring force
  linkDistance: 70,

  // Collision
  collisionRadius: 20,
  collisionStrength: 0.7,
  collisionIterations: 2,

  // DAG & Centering
  dagMode: "zout",
  dagLevelDistance: 80,
  centerStrength: 0.05,

  // Velocity Verlet integration & cooling
  alphaDecay: 0.0228,
  velocityDecay: 0.4,
  alphaMin: 0.001,
};

export class CausalForceSimulation {
  private simulation: any = null;
  private nodes: CausalNode[] = [];
  private links: CausalLink[] = [];
  private config: ForceLayoutConfig;
  private onTickCallback?: (positions: Map<string, { x: number; y: number; z: number }>) => void;
  private onConvergedCallback?: () => void;

  constructor(config: Partial<ForceLayoutConfig> = {}) {
    this.config = { ...DEFAULT_FORCE_CONFIG, ...config };
  }

  public init(nodes: CausalNode[], links: CausalLink[]): void {
    this.stop();
    this.nodes = nodes.map((n) => ({
      ...n,
      x: n.position.x || (Math.random() - 0.5) * 100,
      y: n.position.y || (Math.random() - 0.5) * 100,
      z: n.position.z || 0,
    }));

    // Clone links to prevent mutations
    this.links = links.map((l) => ({ ...l }));

    if (this.config.dagMode === "zout") {
      const layers = computeTopologicalLayers(this.nodes, this.links);
      applyDAGLayering(this.nodes, layers, this.config.dagLevelDistance);
    }

    try {
      this.simulation = forceSimulation(this.nodes, 3)
        .force(
          "charge",
          forceManyBody()
            .strength(this.config.manyBodyStrength)
            .theta(this.config.manyBodyTheta)
            .distanceMin(this.config.manyBodyDistanceMin)
            .distanceMax(this.config.manyBodyDistanceMax)
        )
        .force(
          "link",
          forceLink(this.links)
            .id((d: any) => d.id)
            .distance(this.config.linkDistance)
        )
        .force("center", forceCenter(0, 0, 0))
        .force(
          "collide",
          forceCollide((d: any) => d.radius + 6)
            .iterations(this.config.collisionIterations)
            .strength(this.config.collisionStrength)
        )
        .alphaDecay(this.config.alphaDecay)
        .velocityDecay(this.config.velocityDecay)
        .alphaMin(this.config.alphaMin);

      this.simulation.on("tick", () => {
        const positions = new Map<string, { x: number; y: number; z: number }>();
        for (const n of this.nodes) {
          positions.set(n.id, { x: n.x ?? 0, y: n.y ?? 0, z: n.z ?? 0 });
          n.position.x = n.x ?? 0;
          n.position.y = n.y ?? 0;
          n.position.z = n.z ?? 0;
        }

        if (this.onTickCallback) {
          this.onTickCallback(positions);
        }

        if (this.simulation.alpha() < this.config.alphaMin) {
          if (this.onConvergedCallback) {
            this.onConvergedCallback();
          }
        }
      });

      this.simulation.alpha(1).restart();
    } catch (e) {
      console.warn("d3-force-3d initialization error, using analytical DAG positioning:", e);
      // Fallback layout
      this.runFallbackLayout();
    }
  }

  private runFallbackLayout(): void {
    const layers = computeTopologicalLayers(this.nodes, this.links);
    applyDAGLayering(this.nodes, layers, this.config.dagLevelDistance);

    // Distribute nodes radially on XY within each layer
    const layerGroups = new Map<number, CausalNode[]>();
    for (const n of this.nodes) {
      const l = n.layer ?? 0;
      if (!layerGroups.has(l)) layerGroups.set(l, []);
      layerGroups.get(l)!.push(n);
    }

    layerGroups.forEach((groupNodes) => {
      const count = groupNodes.length;
      const radius = Math.max(40, count * 25);
      groupNodes.forEach((node, i) => {
        const angle = (2 * Math.PI * i) / count;
        node.x = Math.cos(angle) * radius;
        node.y = Math.sin(angle) * radius;
        node.position.x = node.x;
        node.position.y = node.y;
      });
    });

    const positions = new Map<string, { x: number; y: number; z: number }>();
    for (const n of this.nodes) {
      positions.set(n.id, { x: n.position.x, y: n.position.y, z: n.position.z });
    }
    if (this.onTickCallback) this.onTickCallback(positions);
    if (this.onConvergedCallback) this.onConvergedCallback();
  }

  public onTick(cb: (positions: Map<string, { x: number; y: number; z: number }>) => void): void {
    this.onTickCallback = cb;
  }

  public onConverged(cb: () => void): void {
    this.onConvergedCallback = cb;
  }

  public stop(): void {
    if (this.simulation) {
      this.simulation.stop();
      this.simulation = null;
    }
  }

  public restart(): void {
    if (this.simulation) {
      this.simulation.alpha(0.3).restart();
    }
  }
}
