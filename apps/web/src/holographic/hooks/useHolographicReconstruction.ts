/**
 * Master Holographic Reconstruction Orchestration Hook
 * Section 2 & 4.1.4 of Holographic Reconstruction Plan
 */

import { useState, useEffect, useRef, useCallback } from "react";
import * as THREE from "three";
import { CausalNode, CausalLink, QualityMetrics, HologramState } from "../types";
import { generateAmplitudeTarget } from "../holography/amplitudeTarget";
import { PhaseRetrievalEngine } from "../holography/phaseRetrieval";
import { DepthStack } from "../holography/depthStack";
import { phaseToDataTexture, intensityToDataTexture } from "../holography/hologramMaterial";

export interface UseHolographicReconstructionOptions {
  gridSize?: number; // 256, 512, 1024
  wavelength?: number; // 532e-9 m
  pixelPitch?: number; // 8e-6 m
  depthSlices?: number; // 16, 24, 32
  useWorker?: boolean; // Enable Web Worker offload
}

interface WorkerMessage {
  type: "RUN" | "PROGRESS" | "COMPLETE" | "ERROR";
  amplitudeTarget?: Float32Array;
  supportMask?: Float32Array;
  gridSize?: number;
  options?: any;
  progress?: number;
  metrics?: QualityMetrics;
  phase?: Float32Array;
  error?: string;
}

export function useHolographicReconstruction(
  nodes: CausalNode[],
  links: CausalLink[],
  options: UseHolographicReconstructionOptions = {}
) {
  const gridSize = options.gridSize ?? 256;
  const wavelength = options.wavelength ?? 532e-9;
  const pixelPitch = options.pixelPitch ?? 8e-6;
  const depthSlices = options.depthSlices ?? 16;
  const [useWorkerEnabled, setUseWorkerEnabled] = useState(options.useWorker ?? true); // Default to worker for non-blocking UI

  const [state, setState] = useState<HologramState>({
    phaseMap: null,
    amplitudeTarget: null,
    quality: { mse: 0, ssim: 0, strehlRatio: 0, iterations: 0 },
    sliceZ: 0,
    isComputing: false,
    wavelength,
    pixelPitch,
    gridSize,
  });

  const [phaseTexture, setPhaseTexture] = useState<THREE.DataTexture | null>(null);
  const [sliceTexture, setSliceTexture] = useState<THREE.DataTexture | null>(null);
  const [activeDepthIndex, setActiveDepthIndex] = useState(0);

  // Every COMPLETE/slice-change allocates a fresh DataTexture; the replaced
  // one was dropped on the floor with no .dispose(), and unmount leaked the
  // last pair too. The swap helpers below (plus the unmount effect) release
  // GPU-side resources for each replaced texture.
  const phaseTextureRef = useRef<THREE.DataTexture | null>(null);
  const sliceTextureRef = useRef<THREE.DataTexture | null>(null);

  const swapPhaseTexture = useCallback((tex: THREE.DataTexture | null) => {
    const prev = phaseTextureRef.current;
    if (prev && prev !== tex) prev.dispose();
    phaseTextureRef.current = tex;
    setPhaseTexture(tex);
  }, []);

  const swapSliceTexture = useCallback((tex: THREE.DataTexture | null) => {
    const prev = sliceTextureRef.current;
    if (prev && prev !== tex) prev.dispose();
    sliceTextureRef.current = tex;
    setSliceTexture(tex);
  }, []);

  useEffect(() => {
    return () => {
      phaseTextureRef.current?.dispose();
      sliceTextureRef.current?.dispose();
      phaseTextureRef.current = null;
      sliceTextureRef.current = null;
    };
  }, []);

  const phaseEngineRef = useRef<PhaseRetrievalEngine | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const depthStackRef = useRef<DepthStack | null>(null);

  // Initialize Web Worker for phase retrieval
  useEffect(() => {
    if (useWorkerEnabled && typeof Worker !== "undefined") {
      try {
        workerRef.current = new Worker(
          new URL("../workers/phaseRetrievalWorker.ts", import.meta.url),
          { type: "module" }
        );
      } catch (e) {
        console.warn("Failed to create phase retrieval worker, falling back to main thread:", e);
        setUseWorkerEnabled(false);
      }
    }

    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, [useWorkerEnabled]);

  // Handle worker messages
  useEffect(() => {
    const worker = workerRef.current;
    if (!worker) return;

    const handleMessage = async (e: MessageEvent<WorkerMessage>) => {
      const { type, progress, metrics, phase, error } = e.data;

      switch (type) {
        case "PROGRESS":
          setState((prev) => ({
            ...prev,
            isComputing: true,
            quality: metrics ?? prev.quality,
          }));
          break;

        case "COMPLETE":
          if (phase) {
            // 4. Create Three.js phase texture
            const pTex = phaseToDataTexture(phase, gridSize);
            swapPhaseTexture(pTex);

            // 5. Build Depth Stack
            const dStack = new DepthStack({
              gridSize,
              slices: depthSlices,
              zMin: -0.04,
              zMax: 0.04,
            });
            depthStackRef.current = dStack;

            const slices = await dStack.rebuild(phase, {
              lambda: wavelength,
              pixelPitch,
            });

            // Set initial depth slice texture
            if (slices.length > 0) {
              const midSlice = Math.floor(slices.length / 2);
              setActiveDepthIndex(midSlice);
              const sTex = intensityToDataTexture(slices[midSlice], gridSize);
              swapSliceTexture(sTex);
            }

            setState({
              phaseMap: phase,
              // No amplitude copy on this path: the amplitude/support buffers
              // were transferred into the worker (detached on the main
              // thread), and nothing downstream reads this field.
              amplitudeTarget: null,
              quality: metrics ?? { mse: 0, ssim: 0, strehlRatio: 0, iterations: 0 },
              sliceZ: 0,
              isComputing: false,
              wavelength,
              pixelPitch,
              gridSize,
            });
          }
          break;

        case "ERROR":
          console.error("Worker phase retrieval error:", error);
          setState((prev) => ({ ...prev, isComputing: false }));
          break;
      }
    };

    worker.addEventListener("message", handleMessage);
    return () => worker.removeEventListener("message", handleMessage);
    // `useWorkerEnabled` must be a dependency: it's what the worker-CREATION
    // effect above keys on, and whenever that effect can produce a new
    // Worker this listener must re-attach to it — otherwise COMPLETE/ERROR
    // from a recreated worker were silently dropped and `isComputing`
    // stuck true forever.
  }, [gridSize, depthSlices, wavelength, pixelPitch, useWorkerEnabled, swapPhaseTexture, swapSliceTexture]);

  // Initialize or recompute hologram when graph changes
  const reconstructHologram = useCallback(
    async (customIterations: number = 80) => {
      if (nodes.length === 0) return;

      setState((prev) => ({ ...prev, isComputing: true }));

      try {
        // 1. Generate Amplitude Target from 3D layout splats
        const targetRes = generateAmplitudeTarget(nodes, gridSize, 250);

        // 2. Run via Web Worker or fallback to main thread
        const worker = workerRef.current;
        const options = {
          hioIterations: customIterations,
          erIterations1: 20,
          erIterations2: 20,
        };

        if (worker && useWorkerEnabled) {
          // Offload to Web Worker. Transfer the amplitude/support buffers
          // (256KB+ each at grid 256, ~8MB at 1024) with the message instead
          // of letting postMessage structured-clone them — a full copy per
          // reconstruction on both sides of the channel. Ownership moves to
          // the worker; the main-thread views become detached.
          worker.postMessage(
            {
              type: "RUN",
              amplitudeTarget: targetRes.amplitude,
              supportMask: targetRes.supportMask,
              gridSize,
              options,
            },
            [targetRes.amplitude.buffer, targetRes.supportMask.buffer]
          );
        } else {
          // Fallback to main thread
          if (!phaseEngineRef.current || phaseEngineRef.current["N"] !== gridSize) {
            phaseEngineRef.current = new PhaseRetrievalEngine(gridSize);
          }

          const { phase, metrics } = await phaseEngineRef.current.runRetrieval(
            targetRes.amplitude,
            targetRes.supportMask,
            options
          );

          // Process result on main thread
          const pTex = phaseToDataTexture(phase, gridSize);
          swapPhaseTexture(pTex);

          const dStack = new DepthStack({
            gridSize,
            slices: depthSlices,
            zMin: -0.04,
            zMax: 0.04,
          });
          depthStackRef.current = dStack;

          const slices = await dStack.rebuild(phase, {
            lambda: wavelength,
            pixelPitch,
          });

          if (slices.length > 0) {
            const midSlice = Math.floor(slices.length / 2);
            setActiveDepthIndex(midSlice);
            const sTex = intensityToDataTexture(slices[midSlice], gridSize);
            swapSliceTexture(sTex);
          }

          setState({
            phaseMap: phase,
            amplitudeTarget: targetRes.amplitude,
            quality: metrics,
            sliceZ: 0,
            isComputing: false,
            wavelength,
            pixelPitch,
            gridSize,
          });
        }
      } catch (err) {
        console.error("Holographic reconstruction error:", err);
        setState((prev) => ({ ...prev, isComputing: false }));
      }
    },
    [nodes, gridSize, wavelength, pixelPitch, depthSlices, useWorkerEnabled, swapPhaseTexture, swapSliceTexture]
  );

  // Change depth slice
  const setDepthSliceIndex = useCallback(
    (sliceIndex: number) => {
      if (!depthStackRef.current) return;
      const count = depthStackRef.current.getSliceCount();
      const clamped = Math.max(0, Math.min(count - 1, sliceIndex));
      setActiveDepthIndex(clamped);

      const sliceData = depthStackRef.current.getSlice(clamped);
      if (sliceData) {
        const sTex = intensityToDataTexture(sliceData, gridSize);
        swapSliceTexture(sTex);
      }
    },
    [gridSize, swapSliceTexture]
  );

  // Trigger initial reconstruction when nodes first load
  useEffect(() => {
    if (nodes.length > 0 && !state.phaseMap) {
      reconstructHologram(60);
    }
  }, [nodes.length, reconstructHologram, state.phaseMap]);

  return {
    state,
    phaseTexture,
    sliceTexture,
    depthStack: depthStackRef.current,
    activeDepthIndex,
    reconstructHologram,
    setDepthSliceIndex,
  };
}
