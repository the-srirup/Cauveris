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

  const phaseEngineRef = useRef<PhaseRetrievalEngine | null>(null);
  const depthStackRef = useRef<DepthStack | null>(null);
  const targetResultRef = useRef<{ amplitude: Float32Array; supportMask: Float32Array } | null>(null);

  // Initialize or recompute hologram when graph changes
  const reconstructHologram = useCallback(
    async (customIterations: number = 80) => {
      if (nodes.length === 0) return;

      setState((prev) => ({ ...prev, isComputing: true }));

      try {
        // 1. Generate Amplitude Target from 3D layout splats
        const targetRes = generateAmplitudeTarget(nodes, gridSize, 250);
        targetResultRef.current = targetRes;

        // 2. Initialize phase engine
        if (!phaseEngineRef.current || phaseEngineRef.current["N"] !== gridSize) {
          phaseEngineRef.current = new PhaseRetrievalEngine(gridSize);
        }

        // 3. Run Fienup HIO/ER
        const { phase, metrics } = await phaseEngineRef.current.runRetrieval(
          targetRes.amplitude,
          targetRes.supportMask,
          {
            hioIterations: customIterations,
            erIterations1: 20,
            erIterations2: 20,
          }
        );

        // 4. Create Three.js phase texture
        const pTex = phaseToDataTexture(phase, gridSize);
        setPhaseTexture(pTex);

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
          setSliceTexture(sTex);
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
      } catch (err) {
        console.error("Holographic reconstruction error:", err);
        setState((prev) => ({ ...prev, isComputing: false }));
      }
    },
    [nodes, gridSize, wavelength, pixelPitch, depthSlices]
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
        setSliceTexture(sTex);
      }
    },
    [gridSize]
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
