/**
 * Angular Spectrum Method (ASM) Optical Wave Propagation
 * Section 1.1 & 4.2 of Holographic Reconstruction Plan
 *
 * Propagates wavefield U(x,y,0) to depth distance z:
 * U(x,y,z) = IFFT{ FFT{U(x,y,0)} * H(fx, fy, z) }
 *
 * Transfer function:
 * H(fx, fy, z) = exp(i * 2*pi*z * sqrt(1/lambda^2 - fx^2 - fy^2))  (propagating)
 * H(fx, fy, z) = exp(-2*pi*z * sqrt(fx^2 + fy^2 - 1/lambda^2))    (evanescent decay)
 */

import { FastFourierTransform2D, ComplexArray } from "../utils/fft";

export interface PropagationOptions {
  lambda?: number; // Wavelength in meters (default 532nm green laser)
  pixelPitch?: number; // Pixel pitch in meters (default 8um)
  gain?: number; // Intensity visualization gain
  evanescentFade?: number; // 0 = keep, 1 = dampen rapidly
}

export class AngularSpectrumPropagator {
  private N: number;
  private fft: FastFourierTransform2D;
  private buffer: ComplexArray;

  constructor(N: number) {
    this.N = N;
    this.fft = new FastFourierTransform2D(N);
    this.buffer = {
      real: new Float32Array(N * N),
      imag: new Float32Array(N * N),
    };
  }

  /**
   * Propagates a phase map to distance z and returns 2D intensity field |U|^2
   *
   * @param phase Phase map phi in radians [0, 2pi)
   * @param z Propagation distance in meters (e.g. 0.05m = 5cm)
   * @param options Optical parameters
   */
  public propagate(
    phase: Float32Array,
    z: number,
    options: PropagationOptions = {}
  ): Float32Array {
    const N = this.N;
    const total = N * N;
    const lambda = options.lambda ?? 532e-9;
    const pitch = options.pixelPitch ?? 8e-6;
    const gain = options.gain ?? 1.0;
    const evanescentFade = options.evanescentFade ?? 0.8;

    // Step 1: Pack phase into complex field U(x,y,0) = exp(i * phi)
    for (let i = 0; i < total; i++) {
      const p = phase[i];
      this.buffer.real[i] = Math.cos(p);
      this.buffer.imag[i] = Math.sin(p);
    }

    // Step 2: Forward FFT to frequency domain
    this.fft.fft2D(this.buffer, false);

    // Step 3: Shift frequency origin to center to calculate spatial frequencies fx, fy
    this.fft.fftShift(this.buffer);

    // Step 4: Multiply by exact non-paraxial transfer function H(fx, fy, z)
    const invL2 = 1.0 / (lambda * lambda);
    const halfN = N / 2;
    const invGridSpan = 1.0 / (N * pitch);
    const twoPiZ = 2.0 * Math.PI * z;

    for (let y = 0; y < N; y++) {
      const fy = (y - halfN) * invGridSpan;
      const fy2 = fy * fy;
      const rowOffset = y * N;

      for (let x = 0; x < N; x++) {
        const fx = (x - halfN) * invGridSpan;
        const f2 = fx * fx + fy2;
        const arg = invL2 - f2;
        const idx = rowOffset + x;

        let hr = 0;
        let hi = 0;

        if (arg >= 0) {
          // Propagating wave: pure phase shift
          const kz = Math.sqrt(arg);
          const phaseTransfer = twoPiZ * kz;
          hr = Math.cos(phaseTransfer);
          hi = Math.sin(phaseTransfer);
        } else {
          // Evanescent wave: real exponential decay without NaN
          const kzIm = Math.sqrt(-arg);
          const decay = Math.exp(-twoPiZ * kzIm * evanescentFade);
          hr = decay;
          hi = 0.0;
        }

        const ar = this.buffer.real[idx];
        const ai = this.buffer.imag[idx];

        // Complex multiplication: A * H
        this.buffer.real[idx] = ar * hr - ai * hi;
        this.buffer.imag[idx] = ar * hi + ai * hr;
      }
    }

    // Step 5: Shift back from centered frequencies
    this.fft.fftShift(this.buffer);

    // Step 6: Inverse FFT back to spatial domain U(x,y,z)
    this.fft.fft2D(this.buffer, true);

    // Step 7: Calculate intensity |U|^2 and Reinhard tone map
    const intensity = new Float32Array(total);
    for (let i = 0; i < total; i++) {
      const re = this.buffer.real[i];
      const im = this.buffer.imag[i];
      const rawI = (re * re + im * im) * gain;
      // Reinhard tone mapping: I / (1 + I)
      intensity[i] = rawI / (1.0 + rawI);
    }

    return intensity;
  }
}
