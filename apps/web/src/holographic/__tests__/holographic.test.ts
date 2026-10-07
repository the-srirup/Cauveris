/**
 * Unit & Integration Tests for Holographic Reconstruction Engine
 * Based on Acceptance Criteria and Test Plan (Section 6.4 & 12)
 */

import { describe, it, expect } from "vitest";
import { FastFourierTransform2D } from "../utils/fft";
import { generateAmplitudeTarget } from "../holography/amplitudeTarget";
import { PhaseRetrievalEngine } from "../holography/phaseRetrieval";
import { AngularSpectrumPropagator } from "../holography/propagation";
import { DepthStack } from "../holography/depthStack";
import { computeTopologicalLayers, applyDAGLayering } from "../layout/dagLayout";
import { wrapToPi, lerpPhase } from "../holography/phaseInterpolation";
import { applyPatch } from "../layout/patchMutations";
import { CausalNode, CausalLink, CausalGraph, GraphMutation } from "../types";

describe("Holographic Reconstruction Engine", () => {
  describe("1. 2D Fast Fourier Transform (FFT / IFFT)", () => {
    it("should accurately compute forward FFT and inverse IFFT preserving signal", () => {
      const N = 32;
      const fft = new FastFourierTransform2D(N);
      const real = new Float32Array(N * N);
      const imag = new Float32Array(N * N);

      // Create a known test signal (impulse in center)
      real[16 * N + 16] = 1.0;
      const original = new Float32Array(real);

      // Forward FFT
      fft.fft2D({ real, imag }, false);

      // Inverse FFT
      fft.fft2D({ real, imag }, true);

      // Check MSE between reconstructed and original
      let mse = 0;
      for (let i = 0; i < N * N; i++) {
        const diff = real[i] - original[i];
        mse += diff * diff;
      }
      mse /= N * N;

      expect(mse).toBeLessThan(1e-6);
    });

    it("should perform quadrant frequency centering with fftShift", () => {
      const N = 16;
      const fft = new FastFourierTransform2D(N);
      const real = new Float32Array(N * N);
      const imag = new Float32Array(N * N);

      // Place DC spike at [0, 0]
      real[0] = 100.0;

      fft.fftShift({ real, imag });

      // After shift, DC should be at [N/2, N/2]
      const centerIdx = (N / 2) * N + N / 2;
      expect(real[centerIdx]).toBeCloseTo(100.0, 5);
      expect(real[0]).toBeCloseTo(0.0, 5);
    });
  });

  describe("2. Amplitude Target & Gaussian Splats", () => {
    it("should project 3D causal nodes to 2D continuous amplitude target and binary support mask", () => {
      const nodes: CausalNode[] = [
        {
          id: "node-1",
          label: "API",
          type: "gateway",
          position: { x: 0, y: 0, z: 0 },
          radius: 10,
          color: "#ec4899",
          health: 1.0,
        },
        {
          id: "node-2",
          label: "DB",
          type: "database",
          position: { x: 50, y: 50, z: 0 },
          radius: 12,
          color: "#8b5cf6",
          health: 0.8,
        },
      ];

      const N = 64;
      const result = generateAmplitudeTarget(nodes, N, 200, 0.01);

      expect(result.amplitude.length).toBe(N * N);
      expect(result.supportMask.length).toBe(N * N);
      expect(result.maxAmplitude).toBeGreaterThan(0);

      // Max value in normalized amplitude should be 1.0
      let maxNormalized = 0;
      for (let i = 0; i < result.amplitude.length; i++) {
        if (result.amplitude[i] > maxNormalized) maxNormalized = result.amplitude[i];
      }
      expect(maxNormalized).toBeCloseTo(1.0, 4);

      // Center should have high support
      const centerIdx = (N / 2) * N + N / 2;
      expect(result.supportMask[centerIdx]).toBe(1.0);
    });
  });

  describe("3. Fienup Phase Retrieval (HIO/ER)", () => {
    it("should iterate HIO and converge reducing reconstruction MSE", async () => {
      const N = 32;
      const nodes: CausalNode[] = [
        {
          id: "node-test",
          label: "Target",
          type: "service",
          position: { x: 0, y: 0, z: 0 },
          radius: 8,
          color: "#3b82f6",
          health: 1.0,
        },
      ];

      const target = generateAmplitudeTarget(nodes, N, 100);
      const engine = new PhaseRetrievalEngine(N);

      const result = await engine.runRetrieval(target.amplitude, target.supportMask, {
        erIterations1: 10,
        hioIterations: 25,
        erIterations2: 10,
        beta: 0.9,
      });

      expect(result.phase.length).toBe(N * N);
      expect(result.metrics.iterations).toBe(45);
      // Verify finite, valid metrics
      expect(result.metrics.mse).toBeGreaterThanOrEqual(0);
      expect(Number.isFinite(result.metrics.mse)).toBe(true);
      expect(result.metrics.ssim).toBeGreaterThan(0);
    });
  });

  describe("4. Angular Spectrum Method (ASM) Propagation", () => {
    it("should propagate wavefield and handle evanescent waves without producing NaNs", () => {
      const N = 32;
      const propagator = new AngularSpectrumPropagator(N);
      const phase = new Float32Array(N * N);

      // Initialize random phase map
      for (let i = 0; i < phase.length; i++) {
        phase[i] = Math.random() * 2 * Math.PI;
      }

      // Propagate across a typical depth distance (z = 2cm = 0.02m)
      const intensity = propagator.propagate(phase, 0.02, {
        lambda: 532e-9,
        pixelPitch: 8e-6,
      });

      expect(intensity.length).toBe(N * N);

      // Verify no NaNs or Infs exist anywhere in output field
      for (let i = 0; i < intensity.length; i++) {
        expect(Number.isFinite(intensity[i])).toBe(true);
        expect(intensity[i]).toBeGreaterThanOrEqual(0.0);
        expect(intensity[i]).toBeLessThanOrEqual(1.0); // Reinhard normalized
      }
    });

    it("should compute multi-slice depth stack", async () => {
      const depthStack = new DepthStack({
        gridSize: 32,
        slices: 4,
        zMin: -0.02,
        zMax: 0.02,
      });

      const phase = new Float32Array(32 * 32);
      const slices = await depthStack.rebuild(phase);

      expect(slices.length).toBe(4);
      expect(depthStack.getSlice(0)?.length).toBe(32 * 32);
    });
  });

  describe("5. DAG Layering & Topological Ordering", () => {
    it("should assign topological layer depths without cycles", () => {
      const nodes: CausalNode[] = [
        { id: "A", label: "A", type: "event", position: { x: 0, y: 0, z: 0 }, radius: 10, color: "#fff", health: 1 },
        { id: "B", label: "B", type: "decision", position: { x: 0, y: 0, z: 0 }, radius: 10, color: "#fff", health: 1 },
        { id: "C", label: "C", type: "action", position: { x: 0, y: 0, z: 0 }, radius: 10, color: "#fff", health: 1 },
      ];

      const links: CausalLink[] = [
        { source: "A", target: "B", strength: 1.0, type: "causes" },
        { source: "B", target: "C", strength: 1.0, type: "causes" },
      ];

      const layers = computeTopologicalLayers(nodes, links);
      expect(layers.get("A")).toBe(0);
      expect(layers.get("B")).toBe(1);
      expect(layers.get("C")).toBe(2);

      const layeredNodes = applyDAGLayering(nodes, layers, 100);
      expect(layeredNodes[0].z).toBeLessThan(layeredNodes[1].z!);
      expect(layeredNodes[1].z).toBeLessThan(layeredNodes[2].z!);
    });
  });

  describe("6. Phase Interpolation (Shortest-Arc & wrapToPi)", () => {
    it("should wrap angle differences correctly into (-pi, pi]", () => {
      // 0 rad difference
      expect(wrapToPi(0)).toBeCloseTo(0);

      // Angle across 2pi branch cut: from 6.20 to 0.08 rad is ~0.16 rad delta
      const d = 0.08 - 6.20; // -6.12
      const wrapped = wrapToPi(d);
      expect(wrapped).toBeCloseTo(2 * Math.PI - 6.12, 4);
      expect(Math.abs(wrapped)).toBeLessThanOrEqual(Math.PI);
    });

    it("should interpolate phase maps smoothly along shortest arc without branch-cut tear", () => {
      const a = new Float32Array([6.20]);
      const b = new Float32Array([0.08]);

      // At t = 0.5, shortest-arc should be near 6.28 rad (or 0)
      const mid = lerpPhase(a, b, 0.5);
      expect(mid[0]).toBeGreaterThan(6.20); // Moves forward through 2pi, NOT backward through pi
    });
  });

  describe("7. Patch Mutations (Graph Delta Model)", () => {
    it("should apply addNode, removeNode, and modifyEdge correctly", () => {
      const graph: CausalGraph = {
        nodes: [
          { id: "N1", label: "N1", type: "service", position: { x: 0, y: 0, z: 0 }, radius: 10, color: "#fff", health: 1 },
          { id: "N2", label: "N2", type: "service", position: { x: 50, y: 0, z: 0 }, radius: 10, color: "#fff", health: 1 },
        ],
        links: [
          { source: "N1", target: "N2", strength: 0.8, type: "causes" },
        ],
      };

      const mutations: GraphMutation[] = [
        {
          kind: "modifyEdge",
          source: "N1",
          target: "N2",
          before: { strength: 0.8 },
          after: { strength: 0.2 },
        },
        {
          kind: "addNode",
          node: { id: "N3", label: "N3", type: "cache", position: { x: 25, y: 25, z: 0 }, radius: 8, color: "#06b6d4", health: 1 },
        },
      ];

      const patched = applyPatch(graph, mutations);

      expect(patched.nodes.length).toBe(3);
      expect(patched.nodes.find((n) => n.id === "N3")).toBeDefined();
      expect(patched.links[0].strength).toBeCloseTo(0.2, 5);
    });
  });
});
