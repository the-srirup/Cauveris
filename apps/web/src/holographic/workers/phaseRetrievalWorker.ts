/**
 * Web Worker for off-thread Phase Retrieval execution
 */

import { PhaseRetrievalEngine } from "../holography/phaseRetrieval";

let engine: PhaseRetrievalEngine | null = null;
let currentGridSize = 0;

// Under lib.dom, `self` is typed as Window, whose postMessage signature takes
// (message, targetOrigin) — but this file runs in a Worker where the second
// argument is the transfer list. Assert the real worker contract once here.
const postToMain = self.postMessage.bind(self) as unknown as (
  message: unknown,
  transfer?: ArrayBuffer[]
) => void;

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

      // getPhase() returns a fresh copy of the engine's internal buffer, so
      // moving its ArrayBuffer to the main thread costs nothing here — the
      // engine keeps working (the next RUN is unaffected).
      postToMain(
        {
          type: "COMPLETE",
          phase: result.phase,
          metrics: result.metrics,
        },
        // getPhase() allocates the array fresh (`new Float32Array(...)`), so
        // its buffer is a plain ArrayBuffer — TS only types it ArrayBufferLike.
        [result.phase.buffer as ArrayBuffer]
      );
    } catch (err) {
      self.postMessage({ type: "ERROR", error: String(err) });
    }
  }
};
