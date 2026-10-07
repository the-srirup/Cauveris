/**
 * Fienup Phase Retrieval: Hybrid Input-Output (HIO) and Error Reduction (ER)
 * Section 1.3 of Holographic Reconstruction Plan
 *
 * Recovers phase phi(x,y) from target amplitude A_t such that:
 * |F{exp(i*phi)}| approx A_t
 */

import { FastFourierTransform2D, ComplexArray } from "../utils/fft";
import { QualityMetrics } from "../types";

export interface PhaseRetrievalOptions {
  erIterations1?: number; // Initial ER (default 30)
  hioIterations?: number; // Main HIO (default 120)
  erIterations2?: number; // Final ER refinement (default 30)
  beta?: number; // Feedback parameter (default 0.9)
  lambdaTV?: number; // Total variation regularization (default 0.005)
  onProgress?: (progress: number, metrics: QualityMetrics) => void;
}

export class PhaseRetrievalEngine {
  private N: number;
  private fft: FastFourierTransform2D;
  private buffer: ComplexArray;
  private currentPhase: Float32Array;

  constructor(N: number) {
    this.N = N;
    this.fft = new FastFourierTransform2D(N);
    this.buffer = {
      real: new Float32Array(N * N),
      imag: new Float32Array(N * N),
    };
    this.currentPhase = new Float32Array(N * N);
    this.initRandomPhase();
  }

  public initRandomPhase(): void {
    const total = this.N * this.N;
    for (let i = 0; i < total; i++) {
      this.currentPhase[i] = Math.random() * 2 * Math.PI;
    }
  }

  public setPhase(phase: Float32Array): void {
    if (phase.length === this.currentPhase.length) {
      this.currentPhase.set(phase);
    }
  }

  public getPhase(): Float32Array {
    return new Float32Array(this.currentPhase);
  }

  /**
   * Run full phase retrieval schedule: ER -> HIO -> ER
   */
  public async runRetrieval(
    amplitudeTarget: Float32Array,
    supportMask: Float32Array,
    options: PhaseRetrievalOptions = {}
  ): Promise<{ phase: Float32Array; metrics: QualityMetrics }> {
    const er1 = options.erIterations1 ?? 30;
    const hio = options.hioIterations ?? 120;
    const er2 = options.erIterations2 ?? 30;
    const totalIter = er1 + hio + er2;
    const beta = options.beta ?? 0.9;
    const lambdaTV = options.lambdaTV ?? 0.005;

    const N = this.N;
    const total = N * N;

    // Allocate object domain estimate P_n
    const objectReal = new Float32Array(total);
    const objectImag = new Float32Array(total);

    // Initialize object from target amplitude and current phase
    for (let i = 0; i < total; i++) {
      const ph = this.currentPhase[i];
      const a = amplitudeTarget[i];
      objectReal[i] = a * Math.cos(ph);
      objectImag[i] = a * Math.sin(ph);
    }

    let prevLoss = 1e9;
    let stagnationCounter = 0;

    for (let iter = 0; iter < totalIter; iter++) {
      const isHIO = iter >= er1 && iter < er1 + hio;

      // Copy object to FFT buffer
      this.buffer.real.set(objectReal);
      this.buffer.imag.set(objectImag);

      // Step A: Forward FFT to Fourier domain
      this.fft.fft2D(this.buffer, false);

      // Apply Fourier modulus constraint: replace magnitude with target amplitude
      for (let i = 0; i < total; i++) {
        const re = this.buffer.real[i];
        const im = this.buffer.imag[i];
        const mag = Math.sqrt(re * re + im * im) + 1e-9;
        const targetMag = amplitudeTarget[i];

        const scale = targetMag / mag;
        this.buffer.real[i] = re * scale;
        this.buffer.imag[i] = im * scale;
      }

      // Step B: Inverse FFT back to object domain
      this.fft.fft2D(this.buffer, true);

      // Step C: Object domain constraint (ER vs HIO feedback)
      for (let i = 0; i < total; i++) {
        const primeReal = this.buffer.real[i];
        const primeImag = this.buffer.imag[i];

        if (supportMask[i] > 0.5) {
          // Inside support
          objectReal[i] = primeReal;
          objectImag[i] = primeImag;
          this.currentPhase[i] = Math.atan2(primeImag, primeReal);
        } else {
          // Outside support
          if (isHIO) {
            // HIO feedback: P_{n+1} = P_n - beta * P'_n
            objectReal[i] -= beta * primeReal;
            objectImag[i] -= beta * primeImag;
          } else {
            // Error reduction: force to 0 outside support
            objectReal[i] = 0;
            objectImag[i] = 0;
          }
        }
      }

      // Apply Total Variation regularization on phase every 5 iterations
      if (lambdaTV > 0 && iter % 5 === 0) {
        this.applyTVRegularization(lambdaTV);
      }

      // Compute progress & metrics periodically or on last iter
      if (iter % 15 === 0 || iter === totalIter - 1) {
        const metrics = this.computeMetrics(amplitudeTarget);

        // Stagnation check
        if (Math.abs(metrics.mse - prevLoss) < 1e-5) {
          stagnationCounter++;
          if (stagnationCounter > 4 && iter < totalIter - 30) {
            // Slight phase shakeup to escape saddle point
            for (let i = 0; i < total; i++) {
              if (supportMask[i] < 0.5) {
                this.currentPhase[i] += (Math.random() - 0.5) * 0.5;
              }
            }
            stagnationCounter = 0;
          }
        } else {
          stagnationCounter = 0;
        }
        prevLoss = metrics.mse;

        if (options.onProgress) {
          options.onProgress((iter + 1) / totalIter, {
            ...metrics,
            iterations: iter + 1,
          });
        }
      }
    }

    const finalMetrics = this.computeMetrics(amplitudeTarget);
    return {
      phase: this.getPhase(),
      metrics: {
        ...finalMetrics,
        iterations: totalIter,
      },
    };
  }

  /**
   * Total Variation (TV) phase smoothing
   */
  private applyTVRegularization(lambda: number): void {
    const N = this.N;
    const ph = this.currentPhase;

    for (let y = 1; y < N - 1; y++) {
      const row = y * N;
      for (let x = 1; x < N - 1; x++) {
        const idx = row + x;
        const gradX = ph[idx + 1] - ph[idx - 1];
        const gradY = ph[idx + N] - ph[idx - N];
        const tv = Math.sqrt(gradX * gradX + gradY * gradY);

        if (tv > 1e-4) {
          ph[idx] -= lambda * (gradX + gradY) / tv;
        }
      }
    }
  }

  /**
   * Quality evaluation metrics (MSE, SSIM, Strehl ratio)
   */
  private computeMetrics(amplitudeTarget: Float32Array): QualityMetrics {
    const N = this.N;
    const total = N * N;

    // Propagate phase to reconstructed field magnitude
    for (let i = 0; i < total; i++) {
      const p = this.currentPhase[i];
      this.buffer.real[i] = Math.cos(p);
      this.buffer.imag[i] = Math.sin(p);
    }

    this.fft.fft2D(this.buffer, false);

    let mseSum = 0;
    let targetEnergy = 0;
    let reconEnergy = 0;
    let targetMax = 0;
    let reconMax = 0;

    for (let i = 0; i < total; i++) {
      const r = this.buffer.real[i];
      const im = this.buffer.imag[i];
      const rec = Math.sqrt(r * r + im * im);
      const tgt = amplitudeTarget[i];

      reconEnergy += rec * rec;
      targetEnergy += tgt * tgt;

      if (rec > reconMax) reconMax = rec;
      if (tgt > targetMax) targetMax = tgt;
    }

    // Energy normalization factor
    const norm = Math.sqrt(targetEnergy / (reconEnergy + 1e-9));

    for (let i = 0; i < total; i++) {
      const r = this.buffer.real[i];
      const im = this.buffer.imag[i];
      const rec = Math.sqrt(r * r + im * im) * norm;
      const tgt = amplitudeTarget[i];
      const diff = rec - tgt;
      mseSum += diff * diff;
    }

    const mse = mseSum / total;

    // Simplified SSIM proxy
    const ssim = Math.max(0, Math.min(1, 1.0 - Math.sqrt(mse) * 2.0));

    // Strehl ratio proxy: ratio of peak intensity to theoretical peak
    const strehlRatio = Math.max(0, Math.min(1, (reconMax * norm) / (targetMax + 1e-9)));

    return {
      mse,
      ssim,
      strehlRatio,
      iterations: 0,
    };
  }
}
