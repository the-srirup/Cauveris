/**
 * High-performance 2D Fast Fourier Transform (FFT) in pure TypeScript
 * Implementation: In-place Cooley-Tukey Radix-2 with precomputed twiddle factors
 * Supports forward and inverse transforms for square grids N x N (where N is power of 2)
 */

export interface ComplexArray {
  real: Float32Array;
  imag: Float32Array;
}

export class FastFourierTransform2D {
  private N: number;
  private log2N: number;
  private bitReverse: Uint32Array;
  private twiddleCos: Float32Array;
  private twiddleSin: Float32Array;

  constructor(N: number) {
    if ((N & (N - 1)) !== 0) {
      throw new Error(`Grid size N (${N}) must be a power of 2`);
    }
    this.N = N;
    this.log2N = Math.round(Math.log2(N));

    // Precompute bit reversal table
    this.bitReverse = new Uint32Array(N);
    for (let i = 0; i < N; i++) {
      let rev = 0;
      for (let j = 0; j < this.log2N; j++) {
        if ((i >> j) & 1) {
          rev |= 1 << (this.log2N - 1 - j);
        }
      }
      this.bitReverse[i] = rev;
    }

    // Precompute twiddle factors: exp(-2*pi*i*k/N)
    const half = N >> 1;
    this.twiddleCos = new Float32Array(half);
    this.twiddleSin = new Float32Array(half);
    for (let k = 0; k < half; k++) {
      const angle = (-2.0 * Math.PI * k) / N;
      this.twiddleCos[k] = Math.cos(angle);
      this.twiddleSin[k] = Math.sin(angle);
    }
  }

  public getGridSize(): number {
    return this.N;
  }

  /**
   * 1D in-place FFT along a strided 1D array slice
   */
  private transform1D(
    real: Float32Array,
    imag: Float32Array,
    offset: number,
    stride: number,
    inverse: boolean
  ): void {
    const N = this.N;

    // Bit-reversal permutation
    for (let i = 0; i < N; i++) {
      const rev = this.bitReverse[i];
      if (i < rev) {
        const idx1 = offset + i * stride;
        const idx2 = offset + rev * stride;

        const tmpR = real[idx1];
        real[idx1] = real[idx2];
        real[idx2] = tmpR;

        const tmpI = imag[idx1];
        imag[idx1] = imag[idx2];
        imag[idx2] = tmpI;
      }
    }

    // Butterfly stages
    for (let len = 2; len <= N; len <<= 1) {
      const halfLen = len >> 1;
      const step = N / len;

      for (let i = 0; i < N; i += len) {
        for (let k = 0; k < halfLen; k++) {
          const twIdx = k * step;
          let wReal = this.twiddleCos[twIdx];
          let wImag = this.twiddleSin[twIdx];

          if (inverse) {
            wImag = -wImag;
          }

          const uIdx = offset + (i + k) * stride;
          const vIdx = offset + (i + k + halfLen) * stride;

          const vR = real[vIdx];
          const vI = imag[vIdx];

          // Complex multiply: w * v
          const twVR = wReal * vR - wImag * vI;
          const twVI = wReal * vI + wImag * vR;

          const uR = real[uIdx];
          const uI = imag[uIdx];

          real[uIdx] = uR + twVR;
          imag[uIdx] = uI + twVI;
          real[vIdx] = uR - twVR;
          imag[vIdx] = uI - twVI;
        }
      }
    }

    // Normalization for inverse
    if (inverse) {
      for (let i = 0; i < N; i++) {
        const idx = offset + i * stride;
        real[idx] /= N;
        imag[idx] /= N;
      }
    }
  }

  /**
   * 2D Fast Fourier Transform (in-place)
   */
  public fft2D(field: ComplexArray, inverse: boolean = false): void {
    const N = this.N;
    const { real, imag } = field;

    // Transform rows
    for (let y = 0; y < N; y++) {
      this.transform1D(real, imag, y * N, 1, inverse);
    }

    // Transform columns
    for (let x = 0; x < N; x++) {
      this.transform1D(real, imag, x, N, inverse);
    }
  }

  /**
   * Center low frequencies to center of grid (fftshift)
   */
  public fftShift(field: ComplexArray): void {
    const N = this.N;
    const half = N >> 1;
    const { real, imag } = field;

    for (let y = 0; y < half; y++) {
      for (let x = 0; x < half; x++) {
        const i1 = y * N + x;
        const i2 = (y + half) * N + (x + half);
        const i3 = (y + half) * N + x;
        const i4 = y * N + (x + half);

        // Swap quadrant 1 and 4
        let tr = real[i1]; let ti = imag[i1];
        real[i1] = real[i2]; imag[i1] = imag[i2];
        real[i2] = tr; imag[i2] = ti;

        // Swap quadrant 2 and 3
        tr = real[i3]; ti = imag[i3];
        real[i3] = real[i4]; imag[i3] = imag[i4];
        real[i4] = tr; imag[i4] = ti;
      }
    }
  }
}
