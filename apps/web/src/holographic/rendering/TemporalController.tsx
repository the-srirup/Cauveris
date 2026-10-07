/**
 * Temporal Navigation & Shortest-Arc Phase Interpolation
 * Section 5.2 of Holographic Reconstruction Plan
 */

import React, { useState, useEffect, useRef } from "react";
import { Play, Pause, SkipBack, SkipForward, RotateCcw } from "lucide-react";
import { TemporalFrame } from "../types";
import { wrapToPi, lerpPhase } from "../holography/phaseInterpolation";

export { wrapToPi, lerpPhase };

export interface TemporalControllerProps {
  frames: TemporalFrame[];
  currentTime: number; // [0, 1]
  onTimeChange: (time: number, interpolatedPhase?: Float32Array) => void;
  speed?: number;
}

export function TemporalController({
  frames,
  currentTime,
  onTimeChange,
  speed = 1,
}: TemporalControllerProps) {
  const [isPlaying, setIsPlaying] = useState(false);
  const animFrameRef = useRef<number | null>(null);
  const lastTimeRef = useRef<number>(performance.now());

  const frameCount = Math.max(1, frames.length);

  // Animation loop
  useEffect(() => {
    if (!isPlaying) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      return;
    }

    lastTimeRef.current = performance.now();

    const loop = (now: number) => {
      const dt = (now - lastTimeRef.current) / 1000;
      lastTimeRef.current = now;

      const duration = 10 / speed; // 10s base loop
      const nextTime = (currentTime + dt / duration) % 1.0;

      // Sample interpolated phase if frames have phase maps
      let interpolatedPhase: Float32Array | undefined = undefined;
      if (frames.length >= 2) {
        const scaled = nextTime * (frames.length - 1);
        const idx0 = Math.floor(scaled);
        const idx1 = Math.min(idx0 + 1, frames.length - 1);
        const frac = scaled - idx0;

        const p0 = frames[idx0]?.phaseMap;
        const p1 = frames[idx1]?.phaseMap;
        if (p0 && p1) {
          interpolatedPhase = lerpPhase(p0, p1, frac);
        }
      }

      onTimeChange(nextTime, interpolatedPhase);
      animFrameRef.current = requestAnimationFrame(loop);
    };

    animFrameRef.current = requestAnimationFrame(loop);
    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    };
  }, [isPlaying, currentTime, speed, frames, onTimeChange]);

  const handleSeek = (newVal: number) => {
    let interpolatedPhase: Float32Array | undefined = undefined;
    if (frames.length >= 2) {
      const scaled = newVal * (frames.length - 1);
      const idx0 = Math.floor(scaled);
      const idx1 = Math.min(idx0 + 1, frames.length - 1);
      const frac = scaled - idx0;

      const p0 = frames[idx0]?.phaseMap;
      const p1 = frames[idx1]?.phaseMap;
      if (p0 && p1) {
        interpolatedPhase = lerpPhase(p0, p1, frac);
      }
    }
    onTimeChange(newVal, interpolatedPhase);
  };

  const currentFrameIdx = Math.min(
    frameCount - 1,
    Math.floor(currentTime * (frameCount - 1))
  );

  return (
    <div className="flex flex-col gap-2 p-3 bg-slate-900/80 backdrop-blur border border-slate-700/60 rounded-xl text-slate-200">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-sky-400">
          Reality Timeline: Stage {currentFrameIdx + 1} / {frameCount}
        </span>
        <span className="font-mono text-slate-400">{(currentTime * 100).toFixed(1)}%</span>
      </div>

      {/* Scrubber slider */}
      <input
        type="range"
        min={0}
        max={1}
        step={0.005}
        value={currentTime}
        onChange={(e) => handleSeek(parseFloat(e.target.value))}
        className="w-full h-1.5 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-400"
      />

      {/* Playback controls */}
      <div className="flex items-center justify-between mt-1">
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSeek(0)}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
            title="Reset"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => handleSeek(Math.max(0, currentTime - 1 / (frameCount - 1 || 1)))}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
            title="Step Back"
          >
            <SkipBack className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className="p-1.5 rounded bg-sky-500/20 text-sky-400 hover:bg-sky-500/30 font-medium"
            title={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={() => handleSeek(Math.min(1, currentTime + 1 / (frameCount - 1 || 1)))}
            className="p-1.5 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200"
            title="Step Forward"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </button>
        </div>

        <div className="text-[11px] text-slate-400 font-mono">
          Shortest-Arc Phase Interpolation
        </div>
      </div>
    </div>
  );
}
