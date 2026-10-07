/**
 * Depth Stack: Volumetric Depth Slice Computation
 * Section 4.4 of Holographic Reconstruction Plan
 *
 * Precomputes K depth slices U(x,y,z_k) to allow real-time interactive 60 FPS
 * ray-marching/volume sampling without recomputing 47 FFT dispatches per frame.
 */

import { AngularSpectrumPropagator, PropagationOptions } from "./propagation";

export interface DepthStackConfig {
  slices?: number; // Number of depth slices K (e.g. 16, 32, 64)
  zMin?: number; // Minimum depth distance in meters
  zMax?: number; // Maximum depth distance in meters
  gridSize?: number; // N (e.g. 256, 512)
}

export class DepthStack {
  private N: number;
  private K: number;
  private zMin: number;
  private zMax: number;
  private slices: Float32Array[] = [];
  private propagator: AngularSpectrumPropagator;

  constructor(config: DepthStackConfig = {}) {
    this.N = config.gridSize ?? 256;
    this.K = config.slices ?? 24;
    this.zMin = config.zMin ?? -0.05;
    this.zMax = config.zMax ?? 0.05;
    this.propagator = new AngularSpectrumPropagator(this.N);
  }

  public getGridSize(): number {
    return this.N;
  }

  public getSliceCount(): number {
    return this.K;
  }

  public getSlice(index: number): Float32Array | null {
    if (index >= 0 && index < this.slices.length) {
      return this.slices[index];
    }
    return null;
  }

  public getAllSlices(): Float32Array[] {
    return this.slices;
  }

  /**
   * Rebuild all K depth slices across [zMin, zMax]
   */
  public async rebuild(
    phase: Float32Array,
    options: PropagationOptions = {},
    onProgress?: (progress: number) => void
  ): Promise<Float32Array[]> {
    const K = this.K;
    const dz = K > 1 ? (this.zMax - this.zMin) / (K - 1) : 0;
    this.slices = new Array(K);

    for (let k = 0; k < K; k++) {
      const z = this.zMin + k * dz;
      const sliceIntensity = this.propagator.propagate(phase, z, options);
      this.slices[k] = sliceIntensity;

      if (onProgress) {
        onProgress((k + 1) / K);
      }

      // Yield event loop every 4 slices so browser does not freeze
      if (k % 4 === 3) {
        await new Promise((resolve) => setTimeout(resolve, 0));
      }
    }

    return this.slices;
  }
}
