"use client";

import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import {
  PageHeader,
  Badge,
  Button,
  Divider,
  Select,
  Panel,
  PanelSection,
  PanelStack,
  PanelHeader,
  PanelFooter,
  PanelCard,
  PanelDivider,
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
import { AuthGate } from "@/components/AuthGate";
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
  ProvenanceBanner,
  useForceLayout,
  useHolographicReconstruction,
  useCounterfactual,
  VIEW_MODES,
  SCENE_VIEWS,
  QUALITY_TERMS,
  STATUS_TERMS,
  INSTRUMENTATION_TERMS,
  PAGE_TERMS,
  SHELL_CONTEXT,
  COMPONENT_ACTIONS,
  componentDeepLink,
  evidenceCoveragePercent,
  formatObservationWindow,
  TOTAL_BOUNDARY_LAYERS,
  type ViewModeValue,
  type VisualizationMetadata,
} from "@/holographic";

const cardStyles = tv({
  base: `
    rounded-[var(--radius-md)] border border-[var(--color-border-default)] bg-[var(--color-canvas-subtle)] p-[var(--card-padding)]
    transition-colors duration-150 hover:border-[var(--color-border-strong)]
    group cursor-pointer
  `,
});

export default function HolographicReconstructionPage() {
  return (
    <AuthGate redirect="/holographic-reconstruction" loadingLabel="Loading Holographic Reconstruction...">
      <HolographicReconstructionContent />
    </AuthGate>
  );
}

function HolographicReconstructionContent() {
  const { incidentId, judgeMode, engineerMode } = useActiveIncident();
  const { setIncidentContext } = useShell();
  const router = useRouter();

  const [viewMode, setViewMode] = useState<"3d" | "topology" | "timeline">("3d");
  const [fieldMode, setFieldMode] = useState<ViewModeValue>("phase_hue");
  const [displayGain, setDisplayGain] = useState(1.0);
  const [showGhosts, setShowGhosts] = useState(true);
  const [showPatch, setShowPatch] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const [gpuEnabled, setGpuEnabled] = useState(true);
  const [gpuDecayType, setGpuDecayType] = useState<"exponential" | "gamma" | "bi_exponential" | "power_law" | "stretched_exponential">("exponential");
  const [gpuNormalization, setGpuNormalization] = useState<"l1" | "l2" | "max">("l1");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiData, setApiData] = useState<any>(null);

  const [provenanceMetadata, setProvenanceMetadata] = useState<
    VisualizationMetadata | undefined
  >(undefined);

  const [rawNodes, setRawNodes] = useState<CausalNode[]>([]);
  const [rawLinks, setRawLinks] = useState<CausalLink[]>([]);
  const [temporalFrames, setTemporalFrames] = useState<TemporalFrame[]>([]);
  const [currentTime, setCurrentTime] = useState(0);

  const fetchSeqRef = useRef(0);
  const fetchHolographicData = useCallback(async () => {
    if (!incidentId) return;
    const seq = ++fetchSeqRef.current;
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
      if (seq !== fetchSeqRef.current) return;
      setApiData(response);
      const meta =
        response.metadata && typeof response.metadata === "object"
          ? (response.metadata as VisualizationMetadata)
          : undefined;
      setProvenanceMetadata(meta);
      const nodes = (response.bulk_nodes || []).map((n: any) => ({
        id: n.id,
        label: n.name,
        name: n.name,
        type: n.type,
        position: { x: n.position[0], y: n.position[1], z: n.position[2] },
        radius: n.size,
        color: n.color,
        health: n.health,
        metrics: n.metrics,
        confidence: n.confidence,
        config_changed: n.config_changed,
      }));
      const links = (response.bulk_edges || []).map((e: any) => ({
        source: e.source,
        target: e.target,
        strength: e.thickness ? e.thickness / 4 : 0.5,
        type: "causes",
        latency_ms: e.latency_ms,
      }));
      setRawNodes(nodes);
      setRawLinks(links);
      setTemporalFrames(response.temporal_frames || []);
      setError(null);
    } catch (err: any) {
      if (seq !== fetchSeqRef.current) return;
      setError(err.message || "Failed to fetch holographic data");
      setApiData(null);
      setProvenanceMetadata(undefined);
      setRawNodes([]);
      setRawLinks([]);
      setTemporalFrames([]);
    } finally {
      if (seq === fetchSeqRef.current) setLoading(false);
    }
  }, [incidentId, gpuEnabled, gpuDecayType, gpuNormalization, showGhosts]);

  useEffect(() => {
    if (incidentId) {
      setIncidentContext({
        id: incidentId,
        title: SHELL_CONTEXT.title,
        state: "ACTIVE",
        pipelineStage: SHELL_CONTEXT.pipelineStage,
        evidenceCoverage: evidenceCoveragePercent(
          provenanceMetadata?.observed_boundary_layers?.length,
          TOTAL_BOUNDARY_LAYERS
        ),
        modelProvider: gpuEnabled ? "CUDA GPU (C++/pybind11)" : "CPU (NumPy)",
        backendStatus: "online",
        processingMode: judgeMode ? "judge" : engineerMode ? "engineer" : "autonomous",
        isDemonstration: false,
      });
    } else {
      setIncidentContext(null);
    }
  }, [incidentId, judgeMode, engineerMode, gpuEnabled, provenanceMetadata, setIncidentContext]);

  useEffect(() => {
    fetchHolographicData();
  }, [fetchHolographicData]);

  const { nodes: layoutNodes, isConverged, restart: restartLayout } = useForceLayout(
    rawNodes,
    rawLinks,
    {
      dagMode: viewMode === "topology" ? "zout" : "none",
      linkDistance: viewMode === "topology" ? 90 : 70,
    }
  );

  const {
    state: hologramState,
    phaseTexture,
    sliceTexture,
    activeDepthIndex,
    depthSliceCount,
    reconstructHologram,
    setDepthSliceIndex,
  } = useHolographicReconstruction(layoutNodes, rawLinks, {
    gridSize: 256,
    depthSlices: 20,
  });

  const {
    result: cfResult,
    isComputing: isCfComputing,
    intervene,
    reset: resetCf,
  } = useCounterfactual(layoutNodes, rawLinks);

  const sampleMutations: GraphMutation[] = useMemo(
    () => [],
    []
  );

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
    <div className="w-full space-y-5 text-[var(--color-fg-default)]">
      <PageHeader
        title={PAGE_TERMS.title}
        subtitle={
          incidentId
            ? PAGE_TERMS.subtitleWithIncident(incidentId)
            : PAGE_TERMS.subtitleNoIncident
        }
        badge={
          <Badge tone={hologramState.isComputing ? "amber" : "primary"} dot>
            {hologramState.isComputing
              ? STATUS_TERMS.computing.label
              : STATUS_TERMS.idle.label}
          </Badge>
        }
      />

      <ProvenanceBanner metadata={provenanceMetadata} />

      {showControls && (
        <Panel variant="inset" padding="md">
          <PanelHeader
            title="Reconstruction Controls"
            subtitle="View modes, field visualizations, and GPU configuration"
            divider={true}
          />
          <PanelSection dividerBefore={false} className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <Select
                value={viewMode}
                onValueChange={(val: string) =>
                  setViewMode(val as (typeof SCENE_VIEWS)[number]["value"])
                }
                options={SCENE_VIEWS.map((v) => ({ value: v.value, label: v.label }))}
                className="w-48 text-xs"
              />

              <Select
                value={fieldMode}
                onValueChange={(val: string) => setFieldMode(val as ViewModeValue)}
                options={VIEW_MODES.map((m) => ({ value: m.value, label: m.label }))}
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

              <div className="flex items-center gap-2 ml-4 border-l border-[var(--color-border-default)] pl-4">
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
              <div className="flex items-center gap-2 text-xs text-[var(--color-fg-muted)]">
                <span>{PAGE_TERMS.displayGain}:</span>
                <input
                  type="range"
                  min={0.2}
                  max={3.0}
                  step={0.1}
                  value={displayGain}
                  onChange={(e) => setDisplayGain(parseFloat(e.target.value))}
                  className="w-20 h-1 bg-[var(--color-border-default)] rounded appearance-none accent-[var(--color-fg-default)]"
                  aria-label={PAGE_TERMS.displayGain}
                />
                <span className="font-mono w-8">{displayGain.toFixed(1)}x</span>
              </div>

              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  restartLayout();
                  reconstructHologram(80);
                  fetchHolographicData();
                }}
                disabled={loading}
              >
                <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
                {PAGE_TERMS.recompute}
              </Button>
            </div>
          </PanelSection>
        </Panel>
      )}

      {error && (
        <Panel variant="inset" padding="sm" className="bg-rose-500/10 border border-rose-500/20">
          <div className="flex items-center gap-2 text-xs text-rose-400">
            <Activity className="h-3.5 w-3.5" />
            Error: {error}
            <Button size="sm" variant="ghost" onClick={fetchHolographicData} className="ml-2">
              Retry
            </Button>
          </div>
        </Panel>
      )}

      {loading && (
        <Panel variant="inset" padding="sm" className="bg-[var(--color-canvas-subtle)] border border-[var(--color-border-default)]">
          <div className="flex items-center gap-2 text-xs text-[var(--color-fg-default)]">
            <RefreshCw className="h-3.5 w-3.5 animate-spin" />
            Fetching holographic data from GPU-accelerated backend...
          </div>
        </Panel>
      )}

      <PanelStack space="lg" className="grid lg:grid-cols-[1fr_360px] gap-5">
        {/* R3F WebGL / WebGPU Canvas */}
        <div className="relative min-h-[680px] rounded-[var(--radius-md)] overflow-hidden border border-[var(--color-border-default)] bg-[var(--color-canvas-inset)] flex items-center justify-center">
          {rawNodes.length === 0 ? (
            <div className="text-center p-8 max-w-md">
              <Box className="h-12 w-12 mx-auto text-[var(--color-fg-muted)] opacity-50 mb-3" />
              <h3 className="text-sm font-semibold text-[var(--color-fg-default)]">
                No Holographic Reconstruction Data
              </h3>
              <p className="text-xs text-[var(--color-fg-muted)] mt-1">
                {error || "No telemetry components available for this incident. Run inversion to generate 3D state."}
              </p>
              <Button
                size="sm"
                variant="outline"
                className="mt-4"
                onClick={() => fetchHolographicData()}
                disabled={loading}
              >
                <RefreshCw className={`h-3 w-3 mr-1.5 ${loading ? "animate-spin" : ""}`} />
                Retry Fetch
              </Button>
            </div>
          ) : (
            <>
          <Canvas
            camera={{ position: [0, 40, 220], fov: 45, near: 0.1, far: 2000 }}
            gl={{
              antialias: true,
              powerPreference: "high-performance",
              alpha: true,
            }}
          >
            <ambientLight intensity={0.8} />
            <directionalLight position={[100, 150, 100]} intensity={1.0} />
            <pointLight position={[0, 0, 50]} intensity={0.5} color="#e6edf3" />
            <gridHelper args={[400, 40, "#30363d", "#21262d"]} position={[0, -70, 0]} />

            <HologramVolume
              phaseTexture={phaseTexture}
              sliceTexture={sliceTexture}
              displayMode={fieldMode}
              exposure={displayGain}
              planeSize={240}
            />

            <CausalGraph3D
              nodes={layoutNodes}
              links={rawLinks}
              selectedNodeId={selectedNodeId}
              onNodeSelect={setSelectedNodeId}
            />

            <GhostTrajectories
              nodes={layoutNodes}
              counterfactual={cfResult}
              visible={showGhosts}
            />

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

          {fieldMode === "intensity_slice" && (
            <div className="absolute top-4 left-4 p-3 rounded-xl bg-slate-900/90 backdrop-blur border border-slate-700/70 text-xs flex flex-col gap-2 w-64 shadow-xl">
              <div className="flex justify-between items-center text-slate-300">
                <span className="font-semibold text-emerald-400">
                  {PAGE_TERMS.sliceOverlayTitle}
                </span>
                <span className="font-mono">
                  Depth {activeDepthIndex + 1} / {Math.max(1, depthSliceCount)}
                </span>
              </div>
              <input
                type="range"
                min={0}
                max={Math.max(0, depthSliceCount - 1)}
                value={activeDepthIndex}
                onChange={(e) => setDepthSliceIndex(parseInt(e.target.value, 10))}
                className="w-full h-1.5 bg-slate-700 rounded accent-emerald-400"
                aria-label="Bulk depth slice"
              />
            </div>
          )}

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

          <div className="absolute bottom-4 right-4 text-[10px] text-[var(--color-fg-muted)] bg-[var(--color-canvas-inset)] px-2 py-1 rounded-[var(--radius-sm)] border border-[var(--color-border-default)]">
            Keys: <kbd className="text-[var(--color-fg-default)] font-mono">[</kbd> Toggle UI • <kbd className="text-[var(--color-fg-default)] font-mono">G</kbd> Ghosts • <kbd className="text-[var(--color-fg-default)] font-mono">←/→</kbd> Step
          </div>
            </>
          )}
        </div>

        {/* Right Inspector & Physics Telemetry Panel */}
        <PanelStack space="lg">
          <Panel padding="none">
            <PanelHeader
              title={PAGE_TERMS.telemetryCardTitle}
              subtitle="Reconstruction quality metrics and GPU acceleration status"
              divider={true}
            />
            <PanelSection dividerBefore={false} className="space-y-3 text-xs">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-[var(--color-fg-muted)]" title={QUALITY_TERMS.residual.implementationNote}>
                    {QUALITY_TERMS.residual.label}
                  </span>
                  <span className="font-mono text-[var(--color-fg-default)]">
                    {hologramState.quality.mse > 0
                      ? hologramState.quality.mse.toExponential(3)
                      : "Calculating..."}
                  </span>
                </div>
                <div className="w-full h-1.5 bg-[var(--color-canvas-subtle)] rounded-full overflow-hidden">
                  <div
                    className="h-full bg-[var(--color-fg-default)] transition-all duration-300"
                    style={{
                      width: `${Math.min(100, Math.max(5, (1 - hologramState.quality.mse * 10) * 100))}%`,
                    }}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400" title={QUALITY_TERMS.fidelity.implementationNote}>
                    {QUALITY_TERMS.fidelity.label}
                  </span>
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
                  <span
                    className="text-slate-400"
                    title={QUALITY_TERMS.peakRecovery.implementationNote}
                  >
                    {QUALITY_TERMS.peakRecovery.label}
                  </span>
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
                <div title={INSTRUMENTATION_TERMS.observationWindow.implementationNote}>
                  <span className="text-slate-500">
                    {INSTRUMENTATION_TERMS.observationWindow.label}:
                  </span>
                  <div className="font-mono text-slate-300">
                    {formatObservationWindow(provenanceMetadata?.time_window_ns)}
                  </div>
                </div>
                <div title={INSTRUMENTATION_TERMS.samplingGrid.implementationNote}>
                  <span className="text-slate-500">
                    {INSTRUMENTATION_TERMS.samplingGrid.label}:
                  </span>
                  <div className="font-mono text-slate-300">
                    {hologramState.gridSize}×{hologramState.gridSize}
                  </div>
                </div>
                <div title={INSTRUMENTATION_TERMS.layout.implementationNote}>
                  <span className="text-slate-500">
                    {INSTRUMENTATION_TERMS.layout.label}:
                  </span>
                  <div className="font-mono text-emerald-400">
                    {isConverged ? "Converged" : "Relaxing..."}
                  </div>
                </div>
                <div title={INSTRUMENTATION_TERMS.solver.implementationNote}>
                  <span className="text-slate-500">
                    {INSTRUMENTATION_TERMS.solver.label}:
                  </span>
                  <div className="font-mono text-slate-300">
                    {INSTRUMENTATION_TERMS.solver.value}
                  </div>
                </div>
              </div>
            </PanelSection>
          </Panel>

          <Panel padding="none">
            <PanelHeader
              title={selectedNode ? `Component: ${selectedNode.label}` : "Component Inspector"}
              subtitle={selectedNode ? "Click to inspect metrics and simulate counterfactual interventions" : "Select a node in the 3D scene"}
              divider={true}
            />
            <PanelSection dividerBefore={false}>
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
                    <div className="grid grid-cols-2 gap-2 pt-2 border-t border-[var(--color-border-default)]">
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px] flex items-center gap-1">
                          <Cpu className="h-3 w-3" />
                          CPU Usage
                        </div>
                        <div className="font-mono text-[var(--color-fg-default)]">
                          {(selectedNode.metrics.cpu_usage * 100).toFixed(0)}%
                        </div>
                      </Panel>
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px] flex items-center gap-1">
                          <HardDrive className="h-3 w-3" />
                          Memory
                        </div>
                        <div className="font-mono text-[var(--color-fg-default)]">
                          {(selectedNode.metrics.memory_usage * 100).toFixed(0)}%
                        </div>
                      </Panel>
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px] flex items-center gap-1">
                          <Wifi className="h-3 w-3" />
                          Network
                        </div>
                        <div className="font-mono text-emerald-400">
                          {(selectedNode.metrics.network_usage * 100).toFixed(0)}%
                        </div>
                      </Panel>
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px] flex items-center gap-1">
                          <Activity className="h-3 w-3" />
                          P99 Latency
                        </div>
                        <div className="font-mono text-rose-400">
                          {selectedNode.metrics.latency_p99_ms} ms
                        </div>
                      </Panel>
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px]">Error Rate</div>
                        <div className="font-mono text-rose-400">
                          {(selectedNode.metrics.error_rate * 100).toFixed(1)}%
                        </div>
                      </Panel>
                      <Panel variant="inset" padding="sm">
                        <div className="text-[var(--color-fg-muted)] text-[10px]">Confidence</div>
                        <div className="font-mono text-emerald-400">
                          {((selectedNode.confidence ?? 0) * 100).toFixed(0)}%
                        </div>
                      </Panel>
                    </div>
                  )}

                  <PanelDivider label="Counterfactual Intervention" />

                  <div className="pt-2 border-t border-[var(--color-border-default)]">
                    <div className="text-[11px] font-semibold text-[var(--color-fg-default)] mb-2 flex items-center gap-1">
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

                  <PanelDivider label="Continue Investigation" />

                  <div className="pt-2 border-t border-[var(--color-border-default)]">
                    <div className="text-[11px] font-semibold text-[var(--color-fg-default)] mb-2 flex items-center gap-1">
                      <ArrowRight className="h-3.5 w-3.5" />
                      Continue investigating {selectedNode.label}
                    </div>
                    <div className="space-y-1.5">
                      {COMPONENT_ACTIONS.map((action) => (
                        <PanelCard
                          key={action.href}
                          title={action.label}
                          subtitle={action.description}
                          trailing={<ArrowRight className="h-3 w-3 shrink-0 opacity-60" />}
                          hoverable
                          onClick={() =>
                            router.push(
                              componentDeepLink(action.href, selectedNode.id, incidentId)
                            )
                          }
                        />
                      ))}
                    </div>
                    <p className="mt-1.5 text-[10px] leading-snug text-[var(--color-fg-muted)]">
                      Opens the tool with this component and incident already
                      selected.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-[var(--color-fg-muted)] text-xs">
                  <Box className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  Click on any node in the 3D scene to inspect metrics and simulate counterfactual interventions.
                </div>
              )}
            </PanelSection>
          </Panel>

          {cfResult && (
            <Panel padding="none">
              <PanelHeader
                title="Counterfactual Simulation Output"
                subtitle={`Intervention: do(${cfResult.interventionNode} = ${(cfResult.interventionValue * 100).toFixed(0)}%)`}
                divider={true}
              />
              <PanelSection dividerBefore={false} className="space-y-2 text-xs">
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
              </PanelSection>
            </Panel>
          )}
        </PanelStack>
      </PanelStack>

      <Divider className="my-[var(--divider-margin)]" />

      <PanelStack space="lg" className="space-y-5">
        <PanelHeader
          title="Connected Investigation Pipeline"
          subtitle="Navigate to related investigation tools with current context"
          divider={true}
        />
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
            <PanelCard
              key={index}
              title={card.title}
              subtitle={card.desc}
              leading={
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-sm)] bg-[var(--color-canvas-subtle)] text-[var(--color-fg-default)] border border-[var(--color-border-default)]">
                  <card.icon className="h-5 w-5" />
                </div>
              }
              trailing={<ArrowRight className="h-4 w-4 text-[var(--color-fg-muted)] group-hover:text-[var(--color-fg-default)] transition-colors" />}
              hoverable
              onClick={() =>
                router.push(
                  componentDeepLink(card.href, selectedNode?.id ?? null, incidentId)
                )
              }
            />
          ))}
        </div>
      </PanelStack>
    </div>
  );
}