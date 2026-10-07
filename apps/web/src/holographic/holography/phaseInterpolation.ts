/**
 * Shortest-Arc Phase Interpolation
 * Section 5.2 of Holographic Reconstruction Plan
 */

/**
 * Wrap a phase difference into (-pi, pi] to avoid 2pi branch-cut tearing
 */
export function wrapToPi(d: number): number {
  return d - 2 * Math.PI * Math.floor((d + Math.PI) / (2 * Math.PI));
}

/**
 * Shortest-arc linear interpolation of two phase maps
 */
export function lerpPhase(a: Float32Array, b: Float32Array, t: number): Float32Array {
  const len = Math.min(a.length, b.length);
  const out = new Float32Array(len);
  for (let i = 0; i < len; i++) {
    out[i] = a[i] + t * wrapToPi(b[i] - a[i]);
  }
  return out;
}
