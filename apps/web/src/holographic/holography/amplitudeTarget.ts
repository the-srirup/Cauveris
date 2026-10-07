/**
 * Amplitude Target and Support Mask Generation from 3D Causal Graph
 * Section 1.2 & 1.3 of Holographic Reconstruction Plan
 *
 * Projects 3D causal graph nodes onto 2D plane as Gaussian splats:
 * A_t(x,y) = sum_i G(x - x_i, y - y_i; sigma_i) * w_i
 */

import { CausalNode } from "../types";

export interface AmplitudeTargetResult {
  amplitude: Float32Array; // N x N values normalized to [0, 1]
  supportMask: Float32Array; // N x N binary/soft mask in [0, 1]
  maxAmplitude: number;
}

/**
 * Generates continuous target amplitude and support mask from causal nodes
 *
 * @param nodes List of causal nodes with 3D positions
 * @param N Grid resolution (e.g. 512, 1024)
 * @param worldBounds Size of the simulation bounding box in world units
 * @param tau Support threshold fraction (default 0.01)
 */
export function generateAmplitudeTarget(
  nodes: CausalNode[],
  N: number,
  worldBounds: number = 300,
  tau: number = 0.01
): AmplitudeTargetResult {
  const amplitude = new Float32Array(N * N);
  const supportMask = new Float32Array(N * N);

  if (nodes.length === 0) {
    return { amplitude, supportMask, maxAmplitude: 0 };
  }

  const halfN = N / 2;
  const scale = (N * 0.4) / worldBounds; // Scale world units to grid units

  let maxVal = 0;

  for (const node of nodes) {
    // Project node position to grid coordinates (centered)
    const gx = halfN + node.position.x * scale;
    const gy = halfN + node.position.y * scale;

    // Weight by importance / health metric
    const weight = Math.max(0.2, (node.health || 0.8) + (node.confidence || 0.5) * 0.5);
    const radius = Math.max(4, node.radius * scale * 0.8);
    const sigma2 = 2 * radius * radius;

    // Splat kernel radius (3 sigma)
    const extent = Math.ceil(3 * radius);
    const minX = Math.max(0, Math.floor(gx - extent));
    const maxX = Math.min(N - 1, Math.ceil(gx + extent));
    const minY = Math.max(0, Math.floor(gy - extent));
    const maxY = Math.min(N - 1, Math.ceil(gy + extent));

    for (let y = minY; y <= maxY; y++) {
      const dy = y - gy;
      const dy2 = dy * dy;
      const rowOffset = y * N;

      for (let x = minX; x <= maxX; x++) {
        const dx = x - gx;
        const dist2 = dx * dx + dy2;

        const val = weight * Math.exp(-dist2 / sigma2);
        const idx = rowOffset + x;
        amplitude[idx] += val;

        if (amplitude[idx] > maxVal) {
          maxVal = amplitude[idx];
        }
      }
    }
  }

  // Normalize amplitude to [0, 1] and build support mask
  if (maxVal > 0) {
    const invMax = 1.0 / maxVal;
    const threshold = tau;

    for (let i = 0; i < amplitude.length; i++) {
      amplitude[i] *= invMax;
      supportMask[i] = amplitude[i] > threshold ? 1.0 : 0.0;
    }
  }

  return { amplitude, supportMask, maxAmplitude: maxVal };
}
