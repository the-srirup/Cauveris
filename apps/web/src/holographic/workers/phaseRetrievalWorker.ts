/**
 * Web Worker for off-thread Phase Retrieval execution
 */

import { PhaseRetrievalEngine } from "../holography/phaseRetrieval";

let engine: PhaseRetrievalEngine | null = null;
let currentGridSize = 0;

self.onmessage = async (e: MessageEvent) => {
  const { type, amplitudeTarget, supportMask, gridSize, options } = e.data;

  if (type === "RUN") {
    try {
      if (!engine || currentGridSize !== gridSize) {
        engine = new PhaseRetrievalEngine(gridSize);
        currentGridSize = gridSize;
      }

      const result = await engine.runRetrieval(amplitudeTarget, supportMask, {
        ...options,
        onProgress: (progress, metrics) => {
          self.postMessage({ type: "PROGRESS", progress, metrics });
        },
      });

      self.postMessage({
        type: "COMPLETE",
        phase: result.phase,
        metrics: result.metrics,
      });
    } catch (err) {
      self.postMessage({ type: "ERROR", error: String(err) });
    }
  }
};
