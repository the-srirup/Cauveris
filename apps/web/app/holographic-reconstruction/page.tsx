"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stars } from "@react-three/drei";
import {
  PageHeader,
  Card,
  Badge,
  Button,
  Divider,
  Select,
} from "@/components/ui";
import {
  GitBranch,
  FlaskConical,
  Wrench,
  RotateCcw,
  Database,
  ArrowRight,
  Clock,
  Layers,
  Box,
  Activity,
  Zap,
  Sliders,
  Sparkles,
  Play,
  Pause,
  RefreshCw,
  Cpu,
  HardDrive,
  Wifi,
} from "lucide-react";
import { tv } from "tailwind-variants";
import { useActiveIncident } from "@/lib/useIncident";
import { useShell } from "@/lib/useShell";
import { useAuthStore } from "@/lib/auth";
import { api } from "@/lib/api";

import {
  CausalNode,
  CausalLink,
  TemporalFrame,
  GraphMutation,
  CausalGraph3D,
  HologramVolume,
  TemporalController,
  GhostTrajectories,
  PatchMutations,
  useForceLayout,
  useHolographicReconstruction,
  useCounterfactual,
} from "@/holographic";

const cardStyles = tv({
  base: `
    glass ring-glow rounded-2xl border border-[var(--color-border)] p-[var(--card-padding)]
    transition-all duration-200 hover:border-[var(--color-brand-primary)]/30 hover:shadow-lg hover:shadow-[var(--color-brand-primary)]/10
    group cursor-pointer
  `,
});

export default function HolographicReconstructionPage() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { setIncidentContext } = useShell();
  const { isAuthenticated, isLoading: authLoading } = useAuthStore();
  const router = useRouter();

  // Navigation & View State
  const [viewMode, setViewMode] = useState<"3d" | "topology" | "timeline">("3d");
  const [opticalMode, setOpticalMode] = useState<"phase_hue" | "fringe_alarm" | "raw" | "intensity_slice">("phase_hue");
  const [exposure, setExposure] = useState(1.0);
  const [showGhosts, setShowGhosts] = useState(true);
  const [showPatch, setShowPatch] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // GPU Configuration
  const [gpuEnabled, setGpuEnabled] = useState(true);
  const [gpuDecayType, setGpuDecayType] = useState<"exponential" | "gamma" | "bi_exponential" | "power_law" | "stretched_exponential">("exponential");
  const [gpuNormalization, setGpuNormalization] = useState<"l1" | "l2" | "max">("l1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiData, setApiData] = useState<any>(null);

  // Raw Graph Data
  const [rawNodes, setRawNodes] = useState<CausalNode[]>([]);
  const [rawLinks, setRawLinks] = useState<CausalLink[]>([]);
  const [temporalFrames, setTemporalFrames] = useState<TemporalFrame[]>([]);
  const [currentTime, setCurrentTime] = useState(0);

  // Fetch holographic data from API
  const fetchHolographicData = useCallback(async () => {
    if (!incidentId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await api.getHolographicReconstruction(incidentId, {
        enable_counterfactual: showGhosts,
        enable_anomalies: true,
        enable_multiscale: true,
        use_gpu: gpuEnabled,
        gpu_decay_type: gpuDecayType,
        gpu_normalization: gpuNormalization,
        gpu_time_step_ns: 1000000,
        gpu_max_kernel_time_ns: 10000000000,
      });
      setApiData(response.data);
      setRawNodes(response.data.bulk_nodes.map((n: any) => ({
        id: n.id,
        label: n.name,
        name: n.name,
        type: n.type,
        position: n.position,
        radius: n.size,
        color: n.color,
        health: n.health,
        metrics: n.metrics,
        confidence: n.confidence,
        config_changed: n.config_changed,
      })));
      setRawLinks(response.data.bulk_edges.map((e: any) => ({
        source: e.source,
        target: e.target,
        strength: e.thickness / 4,
        type: "causes",
        latency_ms: e.latency_ms,
      })));
    } catch (err: any) {
      setError(err.message || "Failed to fetch holographic data");
      // Fallback to mock data
      loadMockData();
    } finally {
      setLoading(false);
    }
  }, [incidentId, gpuEnabled, gpuDecayType, gpuNormalization, showGhosts]);

  const loadMockData = useCallback(() => {
    const id = incidentId || "INC-CAU-001";

    const initialNodes: CausalNode[] = [
      {
        id: "api-gateway",
        label: "API Gateway",
        name: "API Gateway",
        type: "gateway",
        position: { x: 0, y: 0, z: 0 },
        radius: 12,
        color: "#ec4899",
        health: 0.92,
        metrics: { cpu_usage: 0.45, memory_usage: 0.52, network_usage: 0.65, error_rate: 0.01, latency_p99_ms: 45 },
        confidence: 0.95,
      },
      {
        id: "auth-service",
        label: "Auth Service",
        name: "Auth Service",
        type: "service",
        position: { x: -80, y: 40, z: -40 },
        radius: 10,
        color: "#3b82f6",
        health: 0.88,
        metrics: { cpu_usage: 0.38, memory_usage: 0.42, network_usage: 0.3, error_rate: 0.0, latency_p99_ms: 22 },
        confidence: 0.92,
      },
      {
        id: "user-db",
        label: "User Database",
        name: "User Database",
        type: "database",
        position: { x: -140, y: 30, z: -80 },
        radius: 14,
        color: "#8b5cf6",
        health: 0.95,
        metrics: { cpu_usage: 0.28, memory_usage: 0.68, network_usage: 0.25, error_rate: 0.0, latency_p99_ms: 12 },
        confidence: 0.98,
      },
      {
        id: "payment-svc",
        label: "Payment Service",
        name: "Payment Service",
        type: "service",
        position: { x: 70, y: -30, z: -40 },
        radius: 11,
        color: "#3b82f6",
        health: 0.32, // Degraded
        metrics: { cpu_usage: 0.94, memory_usage: 0.88, network_usage: 0.72, error_rate: 0.18, latency_p99_ms: 450 },
        confidence: 0.89,
        config_changed: true,
      },
      {
        id: "cache-layer",
        label: "Redis Cache",
        name: "Redis Cache",
        type: "cache",
        position: { x: 0, y: 70, z: -30 },
        radius: 9,
        color: "#06b6d4",
        health: 0.58,
        metrics: { cpu_usage: 0.72, memory_usage: 0.89, network_usage: 0.45, error_rate: 0.04, latency_p99_ms: 85 },
        confidence: 0.91,
      },
      {
        id: "message-queue",
        label: "Kafka Queue",
        name: "Kafka Queue",
        type: "message_queue",
        position: { x: 120, y: 20, z: -90 },
        radius: 11,
        color: "#84cc16",
        health: 0.75,
        metrics: { cpu_usage: 0.52, memory_usage: 0.61, network_usage: 0.82, error_rate: 0.02, latency_p99_ms: 35 },
        confidence: 0.94,
      },
      {
        id: "notification-svc",
        label: "Notification Service",
        name: "Notification Service",
        type: "service",
        position: { x: 150, y: -40, z: -130 },
        radius: 9,
        color: "#3b82f6",
        health: 0.82,
        metrics: { cpu_usage: 0.35, memory_usage: 0.4, network_usage: 0.2, error_rate: 0.01, latency_p99_ms: 28 },
        confidence: 0.9,
      },
      {
        id: "monitoring",
        label: "Telemetry Pipeline",
        name: "Telemetry Pipeline",
        type: "monitoring",
        position: { x: -60, y: -70, z: 20 },
        radius: 9,
        color: "#f59e0b",
        health: 0.96,
        metrics: { cpu_usage: 0.22, memory_usage: 0.31, network_usage: 0.55, error_rate: 0.0, latency_p99_ms: 8 },
        confidence: 0.97,
      },
    ];

    const initialLinks: CausalLink[] = [
      { source: "api-gateway", target: "auth-service", strength: 0.85, type: "causes", latency_ms: 8 },
      { source: "auth-service", target: "user-db", strength: 0.9, type: "causes", latency_ms: 12 },
      { source: "api-gateway", target: "payment-svc", strength: 0.95, type: "causes", latency_ms: 65 },
      { source: "payment-svc", target: "message-queue", strength: 0.8, type: "causes", latency_ms: 24 },
      { source: "message-queue", target: "notification-svc", strength: 0.75, type: "causes", latency_ms: 18 },
      { source: "api-gateway", target: "cache-layer", strength: 0.6, type: "enables", latency_ms: 6 },
      { source: "payment-svc", target: "cache-layer", strength: 0.7, type: "inhibits", latency_ms: 45 },
      { source: "monitoring", target: "api-gateway", strength: 0.4, type: "correlates", latency_ms: 5 },
    ];

    setRawNodes(initialNodes);
    setRawLinks(initialLinks);

    // Setup 4 temporal frames representing incident progression
    const f1: TemporalFrame = {
      stageId: "T0_NOMINAL",
      timestamp: Date.now() - 3600000,
      nodes: initialNodes.map((n) => ({ ...n, health: 0.95 })),
      links: initialLinks,
    };
    const f2: TemporalFrame = {
      stageId: "T1_CACHE_PRESSURE",
      timestamp: Date.now() - 2400000,
      nodes: initialNodes.map((n) => (n.id === "cache-layer" ? { ...n, health: 0.6 } : n)),
      links: initialLinks,
    };
    const f3: TemporalFrame = {
      stageId: "T2_PAYMENT_CASCADE",
      timestamp: Date.now() - 1200000,
      nodes: initialNodes,
      links: initialLinks,
    };
    const f4: TemporalFrame = {
      stageId: "T3_CURRENT",
      timestamp: Date.now(),
      nodes: initialNodes,
      links: initialLinks,
    };
    setTemporalFrames([f1, f2, f3, f4]);

    setIncidentContext({
      id,
      title: "Holographic 3D Causal Reconstruction",
      state: "ACTIVE",
      pipelineStage: "HOLOGRAPHIC_RECONSTRUCTION",
      evidenceCoverage: 0.94,
      modelProvider: gpuEnabled ? "CUDA GPU (C++/pybind11)" : "CPU (NumPy)",
      backendStatus: "online",
      processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
      isDemonstration: false,
    });
  }, [incidentId, judgeMode, engineerMode, setIncidentContext]);

  // Fetch data on mount and when GPU settings change
  useEffect(() => {
    fetchHolographicData();
  }, [fetchHolographicData]);

  // Force Layout Hook
  const { nodes: layoutNodes, isConverged, restart: restartLayout } = useForceLayout(
    rawNodes,
    rawLinks,
    {
      dagMode: viewMode === "topology" ? "zout" : "none",
      linkDistance: viewMode === "topology" ? 90 : 70,
    }
  );

  // Holographic Master Reconstruction Hook
  const {
    state: hologramState,
    phaseTexture,
    sliceTexture,
    activeDepthIndex,
    reconstructHologram,
    setDepthSliceIndex,
  } = useHolographicReconstruction(layoutNodes, rawLinks, {
    gridSize: 256,
    depthSlices: 20,
  });

  // Counterfactual SCM Hook
  const {
    result: cfResult,
    isComputing: isCfComputing,
    intervene,
    reset: resetCf,
  } = useCounterfactual(layoutNodes, rawLinks);

  // Graph Mutations for Patches
  const sampleMutations: GraphMutation[] = useMemo(
    () => [
      {
        kind: "modifyEdge",
        source: "payment-svc",
        target: "cache-layer",
        before: { strength: 0.7 },
        after: { strength: 0.1 },
      },
    ],
    []
  );

  // Keyboard Shortcuts ([ = toggle UI, Space = play/pause, G = toggle ghosts)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if (e.key === "[") {
        setShowControls((prev) => !prev);
      } else if (e.key === "g" || e.key === "G") {
        setShowGhosts((prev) => !prev);
      } else if (e.key === "ArrowRight") {
        setCurrentTime((prev) => Math.min(1.0, prev + 0.1));
      } else if (e.key === "ArrowLeft") {
        setCurrentTime((prev) => Math.max(0.0, prev - 0.1));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const selectedNode = useMemo(
    () => layoutNodes.find((n) => n.id === selectedNodeId) || null,
    [layoutNodes, selectedNodeId]
  );

  return (
    <div className="flex flex-col gap-[var(--section-gap)] text-[var(--color-text-primary)]">
      <PageHeader
        title="Holographic Reconstruction Engine"
        subtitle={
          incidentId
            ? `Incident: ${incidentId} • Scalar Diffraction & Phase Retrieval`
            : "Optical Wavefront & 3D Causal Graph Synthesis"
        }
        badge={
          <Badge tone={hologramState.isComputing ? "amber" : "primary"} dot>
            {hologramState.isComputing ? "Synthesizing Hologram..." : "Diffraction Online"}
          </Badge>
        }
      />

      {/* Main Control Strip */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl bg-slate-900/60 backdrop-blur border border-slate-800">
        <div className="flex flex-wrap items-center gap-3">
          <Select
            value={viewMode}
            onValueChange={(val: string) => setViewMode(val as any)}
            options={[
              { value: "3d", label: "3D Hologram Volume" },
              { value: "topology", label: "Causal DAG Topology" },
              { value: "timeline", label: "Reality Rewind Timeline" },
            ]}
            className="w-48 text-xs"
          />

          <Select
            value={opticalMode}
            onValueChange={(val: string) => setOpticalMode(val as any)}
            options={[
              { value: "phase_hue", label: "Phase-Hue Wavefront" },
              { value: "fringe_alarm", label: "Fringe Aliasing Warning" },
              { value: "intensity_slice", label: "ASM Intensity Slice" },
              { value: "raw", label: "Raw Phase Grayscale" },
            ]}
            className="w-52 text-xs"
          />

          <Button
            size="sm"
            variant={showGhosts ? "primary" : "secondary"}
            onClick={() => setShowGhosts(!showGhosts)}
          >
            <FlaskConical className="h-3.5 w-3.5 mr-1.5" />
            Ghost Trajectories {showGhosts ? "ON" : "OFF"}
          </Button>

          <Button
            size="sm"
            variant={showPatch ? "primary" : "secondary"}
            onClick={() => setShowPatch(!showPatch)}
          >
            <Wrench className="h-3.5 w-3.5 mr-1.5" />
            Patch Forge Preview
          </Button>

          {/* GPU Configuration Panel */}
          <div className="flex items-center gap-2 ml-4 border-l border-slate-700 pl-4">
            <Button
              size="sm"
              variant={gpuEnabled ? "primary" : "secondary"}
              onClick={() => setGpuEnabled(!gpuEnabled)}
              className="flex items-center gap-1"
            >
              <Cpu className="h-3.5 w-3.5" />
              GPU {gpuEnabled ? "ON" : "OFF"}
            </Button>
            {gpuEnabled && (
              <>
                <Select
                  value={gpuDecayType}
                  onValueChange={(val: string) => setGpuDecayType(val as any)}
                  options={[
                    { value: "exponential", label: "Exp Decay" },
                    { value: "gamma", label: "Gamma" },
                    { value: "bi_exponential", label: "Bi-Exp" },
                    { value: "power_law", label: "Power Law" },
                    { value: "stretched_exponential", label: "Stretched Exp" },
                  ]}
                  className="w-36 text-[10px]"
                />
                <Select
                  value={gpuNormalization}
                  onValueChange={(val: string) => setGpuNormalization(val as any)}
                  options={[
                    { value: "l1", label: "L1 Norm" },
                    { value: "l2", label: "L2 Norm" },
                    { value: "max", label: "Max Norm" },
                  ]}
                  className="w-28 text-[10px]"
                />
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-400">
            <span>Exposure:</span>
            <input
              type="range"
              min={0.2}
              max={3.0}
              step={0.1}
              value={exposure}
              onChange={(e) => setExposure(parseFloat(e.target.value))}
              className="w-20 h-1 bg-slate-700 rounded appearance-none accent-sky-400"
            />
            <span className="font-mono w-8">{exposure.toFixed(1)}x</span>
          </div>

          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              restartLayout();
              reconstructHologram(80);
              fetchHolographicData(); // Re-fetch with new GPU settings
            }}
            disabled={loading}
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
            Re-Synthesize
          </Button>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-lg bg-rose-500/20 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
          <Activity className="h-3.5 w-3.5" />
          Error: {error}
          <Button size="sm" variant="ghost" onClick={fetchHolographicData} className="ml-2">
            Retry
          </Button>
        </div>
      )}

      {loading && (
        <div className="p-3 rounded-lg bg-sky-500/20 border border-sky-500/30 text-sky-300 text-xs flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5 animate-spin" />
          Fetching holographic data from GPU-accelerated backend...
        </div>
      )}

      {/* 3D Visualizer Canvas & Inspection Workspace */}
      <div className="grid lg:grid-cols-[1fr_360px] gap-[var(--section-gap)]">
        {/* R3F WebGL / WebGPU Canvas */}
        <div className="relative min-h-[680px] rounded-2xl overflow-hidden border border-slate-800 bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
          <Canvas
            camera={{ position: [0, 40, 220], fov: 45, near: 0.1, far: 2000 }}
            gl={{
              antialias: true,
              powerPreference: "high-performance",
              alpha: true,
            }}
          >
            <ambientLight intensity={0.6} />
            <directionalLight position={[100, 150, 100]} intensity={1.2} />
            <pointLight position={[0, 0, 50]} intensity={0.8} color="#38bdf8" />
            <Stars radius={400} depth={80} count={1800} factor={3} saturation={0} fade />
            <gridHelper args={[400, 30, "#334155", "#1e293b"]} position={[0, -70, 0]} />

            {/* Optical Hologram Wavefront Volume Plane */}
            <HologramVolume
              phaseTexture={phaseTexture}
              sliceTexture={sliceTexture}
              displayMode={opticalMode}
              exposure={exposure}
              planeSize={240}
            />

            {/* 3D Causal Graph */}
            <CausalGraph3D
              nodes={layoutNodes}
              links={rawLinks}
              selectedNodeId={selectedNodeId}
              onNodeSelect={setSelectedNodeId}
            />

            {/* Ghost Trajectories (Counterfactual Simulation Overlay) */}
            <GhostTrajectories
              nodes={layoutNodes}
              counterfactual={cfResult}
              visible={showGhosts}
            />

            {/* Patch Mutations Overlay */}
            <PatchMutations
              mutations={sampleMutations}
              nodes={layoutNodes}
              visible={showPatch}
            />

            <OrbitControls
              enablePan={true}
              enableZoom={true}
              enableRotate={true}
              minDistance={30}
              maxDistance={700}
              dampingFactor={0.05}
            />
          </Canvas>

          {/* Floating Depth Slice Scrubber Overlay */}
          {opticalMode === "intensity_slice" && (
            <div className="absolute top-4 left-4 p-3 rounded-xl bg-slate-900/90 backdrop-blur border border-slate-700/70 text-xs flex flex-col gap-2 w-64 shadow-xl">
              <div className="flex justify-between items-center text-slate-300">
                <span className="font-semibold text-emerald-400">ASM Propagation Slice</span>
                <span className="font-mono">z = {((activeDepthIndex - 10) * 4).toFixed(0)} mm</span>
              </div>
              <input
                type="range"
                min={0}
                max={19}
                value={activeDepthIndex}
                onChange={(e) => setDepthSliceIndex(parseInt(e.target.value, 10))}
                className="w-full h-1.5 bg-slate-700 rounded accent-emerald-400"
              />
            </div>
          )}

          {/* Bottom Timeline Scrubber */}
          {viewMode === "timeline" && (
            <div className="absolute bottom-4 left-4 right-4 max-w-xl mx-auto">
              <TemporalController
                frames={temporalFrames}
                currentTime={currentTime}
                onTimeChange={(t) => setCurrentTime(t)}
                speed={1.0}
              />
            </div>
          )}

          {/* Keyboard Shortcuts Hint */}
          <div className="absolute bottom-4 right-4 text-[10px] text-slate-400 bg-slate-950/80 px-2 py-1 rounded border border-slate-800">
            Keys: <kbd className="text-sky-400 font-mono">[</kbd> Toggle UI • <kbd className="text-sky-400 font-mono">G</kbd> Ghosts • <kbd className="text-sky-400 font-mono">←/→</kbd> Step
          </div>
        </div>

        {/* Right Inspector & Physics Telemetry Panel */}
        <div className="flex flex-col gap-[var(--section-gap)]">
          {/* Wavefront Quality Telemetry */}
          <Card title="Hologram Reconstruction Telemetry">
            <div className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400">Mean Squared Error (MSE)</span>
                  <span className="font-mono text-sky-400">
                    {hologramState.quality.mse > 0
                      ? hologramState.quality.mse.toExponential(3)
                      : "Calculating..."}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-sky-400 transition-all duration-300"
                    style={{
                      width: `${Math.min(100, Math.max(5, (1 - hologramState.quality.mse * 10) * 100))}%`,
                    }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400">Structural Similarity (SSIM)</span>
                  <span className="font-mono text-emerald-400 font-bold">
                    {(hologramState.quality.ssim * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-emerald-400 transition-all duration-300"
                    style={{ width: `${hologramState.quality.ssim * 100}%` }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400">Strehl Ratio</span>
                  <span className="font-mono text-amber-400 font-bold">
                    {(hologramState.quality.strehlRatio * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber-400 transition-all duration-300"
                    style={{ width: `${hologramState.quality.strehlRatio * 100}%` }}
                  />
                </div>
              </div>

              {/* GPU Acceleration Status */}
              <div className="flex justify-between mb-1 p-2 rounded bg-slate-800/50 border border-slate-700/50">
                <span className="text-slate-400 flex items-center gap-2">
                  <Cpu className="h-3.5 w-3.5" />
                  Compute Backend
                </span>
                <span className={`font-mono font-bold ${gpuEnabled ? "text-emerald-400" : "text-amber-400"}`}>
                  {gpuEnabled ? "CUDA GPU Active" : "CPU Fallback"}
                </span>
              </div>
              {gpuEnabled && (
                <div className="grid grid-cols-2 gap-2 pt-1 text-[11px]">
                  <div>
                    <span className="text-slate-500">Decay:</span>
                    <div className="font-mono text-slate-300">{gpuDecayType}</div>
                  </div>
                  <div>
                    <span className="text-slate-500">Normalization:</span>
                    <div className="font-mono text-slate-300">{gpuNormalization}</div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800 text-[11px]">
                <div>
                  <span className="text-slate-500">Wavelength:</span>
                  <div className="font-mono text-slate-300">532 nm (Green)</div>
                </div>
                <div>
                  <span className="text-slate-500">Pixel Pitch:</span>
                  <div className="font-mono text-slate-300">8.0 µm</div>
                </div>
                <div>
                  <span className="text-slate-500">Layout State:</span>
                  <div className="font-mono text-emerald-400">
                    {isConverged ? "Converged" : "Relaxing..."}
                  </div>
                </div>
                <div>
                  <span className="text-slate-500">Algorithm:</span>
                  <div className="font-mono text-slate-300">Fienup HIO/ER</div>
                </div>
              </div>
            </div>
          </Card>

          {/* Node Inspector */}
          <Card title={selectedNode ? `Component: ${selectedNode.label}` : "Component Inspector"}>
            {selectedNode ? (
              <div className="space-y-3 text-xs">
                <div className="flex items-center gap-2">
                  <div
                    className="w-3.5 h-3.5 rounded-full"
                    style={{ backgroundColor: selectedNode.color }}
                  />
                  <span className="font-semibold text-sm">{selectedNode.label}</span>
                  <Badge tone="muted" className="text-[10px] ml-auto uppercase">
                    {selectedNode.type}
                  </Badge>
                </div>

                <div>
                  <div className="flex justify-between text-xs mb-1">
                    <span className="text-slate-400">Health State</span>
                    <span
                      className={`font-mono font-bold ${
                        selectedNode.health > 0.7
                          ? "text-emerald-400"
                          : selectedNode.health > 0.4
                          ? "text-amber-400"
                          : "text-rose-400"
                      }`}
                    >
                      {(selectedNode.health * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${selectedNode.health * 100}%`,
                        backgroundColor:
                          selectedNode.health > 0.7
                            ? "#10b981"
                            : selectedNode.health > 0.4
                            ? "#f59e0b"
                            : "#ef4444",
                      }}
                    />
                  </div>
                </div>

                {selectedNode.metrics && (
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800">
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px] flex items-center gap-1">
                        <Cpu className="h-3 w-3" />
                        CPU Usage
                      </div>
                      <div className="font-mono text-sky-400">
                        {(selectedNode.metrics.cpu_usage * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px] flex items-center gap-1">
                        <HardDrive className="h-3 w-3" />
                        Memory
                      </div>
                      <div className="font-mono text-amber-400">
                        {(selectedNode.metrics.memory_usage * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px] flex items-center gap-1">
                        <Wifi className="h-3 w-3" />
                        Network
                      </div>
                      <div className="font-mono text-emerald-400">
                        {(selectedNode.metrics.network_usage * 100).toFixed(0)}%
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px] flex items-center gap-1">
                        <Activity className="h-3 w-3" />
                        P99 Latency
                      </div>
                      <div className="font-mono text-rose-400">
                        {selectedNode.metrics.latency_p99_ms} ms
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px]">Error Rate</div>
                      <div className="font-mono text-rose-400">
                        {(selectedNode.metrics.error_rate * 100).toFixed(1)}%
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-800/40">
                      <div className="text-slate-500 text-[10px]">Confidence</div>
                      <div className="font-mono text-emerald-400">
                        {((selectedNode.confidence ?? 0) * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                )}

                {/* Counterfactual Intervention Control */}
                <div className="pt-2 border-t border-slate-800">
                  <div className="text-[11px] font-semibold text-sky-400 mb-2 flex items-center gap-1">
                    <FlaskConical className="h-3.5 w-3.5" />
                    Pearl do(X) Counterfactual Intervention
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="primary"
                      className="flex-1 text-xs"
                      onClick={() => intervene(selectedNode.id, 0.95)}
                      disabled={isCfComputing}
                    >
                      Simulate Heal to 95%
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="text-xs"
                      onClick={resetCf}
                    >
                      Reset
                    </Button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-slate-500 text-xs">
                <Box className="h-8 w-8 mx-auto mb-2 text-slate-600" />
                Click on any node in the 3D scene to inspect metrics and simulate counterfactual interventions.
              </div>
            )}
          </Card>

          {/* Counterfactual Results Summary */}
          {cfResult && (
            <Card title="Counterfactual Simulation Output">
              <div className="space-y-2 text-xs">
                <div className="text-slate-400 text-[11px]">
                  Intervention Applied:{" "}
                  <span className="font-semibold text-sky-400">
                    do({cfResult.interventionNode} = {(cfResult.interventionValue * 100).toFixed(0)}%)
                  </span>
                </div>
                <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                  {cfResult.diff
                    .filter((d) => Math.abs(d.valueDelta) > 0.01)
                    .map((d) => (
                      <div
                        key={d.nodeId}
                        className="p-1.5 rounded bg-slate-800/40 border border-slate-700/50 flex items-center justify-between"
                      >
                        <span className="font-mono text-slate-300">{d.nodeId}</span>
                        <span
                          className={`font-mono font-bold ${
                            d.valueDelta > 0 ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {d.valueDelta > 0 ? "+" : ""}
                          {(d.valueDelta * 100).toFixed(0)}% (Attr: {(d.attribution * 100).toFixed(0)}%)
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>

      <Divider className="my-[var(--divider-margin)]" />

      {/* Investigation Pipeline Tools */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            Connected Investigation Pipeline
          </h2>
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[
            {
              icon: Clock,
              title: "Reality Rewind",
              desc: "Chronological incident playback & temporal scrubbing",
              href: "/reality-rewind",
            },
            {
              icon: GitBranch,
              title: "Causal Constellation",
              desc: "DAG dependency analysis & longest causal chain tracing",
              href: "/causal-constellation",
            },
            {
              icon: FlaskConical,
              title: "Ghost Lab",
              desc: "Pearl counterfactual abduction, action & prediction",
              href: "/ghost-lab",
            },
            {
              icon: Wrench,
              title: "Patch Forge",
              desc: "Synthesize graph mutations & test remediation",
              href: "/patch-forge",
            },
            {
              icon: RotateCcw,
              title: "Victory Replay",
              desc: "Factual vs counterfactual before-and-after audit",
              href: "/victory-replay",
            },
            {
              icon: Database,
              title: "Evidence Vault",
              desc: "Cryptographic telemetry provenance & artifact inventory",
              href: "/evidence-vault",
            },
          ].map((card, index) => (
            <a key={index} href={card.href} className={cardStyles()}>
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-sky-500/10 text-sky-400">
                  <card.icon className="h-5 w-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="font-medium text-slate-100">{card.title}</h3>
                  <p className="mt-1 text-sm text-slate-400">{card.desc}</p>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <Badge tone="success" dot className="text-[10px]">
                  Online
                </Badge>
                <ArrowRight className="h-4 w-4 text-slate-500 group-hover:text-sky-400 transition-colors" />
              </div>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}