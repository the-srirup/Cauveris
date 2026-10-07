/**
 * Hook for managing Fienup Phase Retrieval computation
 */

import { useState, useCallback, useRef } from "react";
import { QualityMetrics } from "../types";
import { PhaseRetrievalEngine } from "../holography/phaseRetrieval";

export function usePhaseRetrieval(gridSize: number = 256) {
  const [phaseMap, setPhaseMap] = useState<Float32Array | null>(null);
  const [quality, setQuality] = useState<QualityMetrics>({
    mse: 0,
    ssim: 0,
    strehlRatio: 0,
    iterations: 0,
  });
  const [isComputing, setIsComputing] = useState(false);
  const [progress, setProgress] = useState(0);

  const engineRef = useRef<PhaseRetrievalEngine | null>(null);

  const computePhase = useCallback(
    async (
      amplitudeTarget: Float32Array,
      supportMask: Float32Array,
      options: { hioIterations?: number } = {}
    ) => {
      setIsComputing(true);
      setProgress(0);

      try {
        if (!engineRef.current) {
          engineRef.current = new PhaseRetrievalEngine(gridSize);
        }

        const result = await engineRef.current.runRetrieval(amplitudeTarget, supportMask, {
          hioIterations: options.hioIterations ?? 90,
          erIterations1: 20,
          erIterations2: 20,
          onProgress: (p, metrics) => {
            setProgress(p);
            setQuality(metrics);
          },
        });

        setPhaseMap(result.phase);
        setQuality(result.metrics);
        setProgress(1.0);
        return result.phase;
      } catch (err) {
        console.error("Phase retrieval failed:", err);
        return null;
      } finally {
        setIsComputing(false);
      }
    },
    [gridSize]
  );

  return {
    phaseMap,
    quality,
    isComputing,
    progress,
    computePhase,
  };
}
