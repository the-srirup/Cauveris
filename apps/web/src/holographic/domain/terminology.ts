/**
 * Robotics-domain vocabulary for the Holographic Reconstruction feature.
 *
 * The reconstruction engine really is a scalar-diffraction / phase-retrieval
 * solver (see ../holography/*). That vocabulary is accurate to the
 * *implementation*, and it is kept there — `wavelength`, `pixelPitch`,
 * `strehlRatio` and the Fienup HIO/ER iteration schedule still name exactly
 * what they are.
 *
 * What it is not is *legible* to the person this feature exists for: a
 * reliability engineer triaging an autonomous-robot fleet incident. The 2026
 * production survey graded robotics mission relevance at 65% and named the
 * literal optical framing its single largest "Conceptual Mismatch Risk" —
 * "de-emphasize the literal optical laser simulation".
 *
 * This module is the one place that translation happens. Every user-facing
 * string that names a reconstruction concept is read from here, so the
 * physics and the presentation cannot drift back together.
 *
 * Two rules govern what is in here:
 *
 *  1. **Never rename toward a claim the data cannot support.** Each term is
 *     backed by a quantity the backend actually emits — a node's `confidence`,
 *     the reconstruction's `time_window_ns`, its `missing_layers`. Nothing is
 *     relabelled into a metric that does not exist.
 *  2. **Keep the implementation note.** `implementationNote` preserves the
 *     exact computation behind each label, so an engineer who *does* want to
 *     know how the number was produced can find out without reading GLSL.
 */

export interface Term {
  /** User-facing label. Never mentions optics or lasers. */
  label: string;
  /** One sentence: what this number means for the system under investigation. */
  description: string;
  /**
   * The computation this label stands in for. Surfaced as a tooltip so the
   * rename never obscures how the value was derived.
   */
  implementationNote: string;
  /**
   * Optional terse form for narrow telemetry cells, where `implementationNote`
   * is a full sentence and would wrap. Only set where a term is rendered as a
   * key/value pair rather than a tooltip.
   */
  value?: string;
}

/**
 * The reconstruction-quality triple.
 *
 * All three are computed from the reconstructed amplitude field
 * (holography/phaseRetrieval.ts `computeMetrics`). That field is built by
 * splatting each component weighted by `health` and `confidence`
 * (holography/amplitudeTarget.ts), which is why these read as statements
 * about state recovery rather than about light.
 */
export const QUALITY_TERMS = {
  /** Was `Mean Squared Error (MSE)`. */
  residual: {
    label: "Reconstruction Residual",
    description:
      "How far the reconstructed component-state field sits from the observed health and confidence field. Lower is better; a rising residual means the graph on screen and the telemetry disagree.",
    implementationNote:
      "Mean squared error of the recovered amplitude against the target amplitude built from node health and confidence (phaseRetrieval.ts, computeMetrics).",
  },
  /** Was `Structural Similarity (SSIM)`. */
  fidelity: {
    label: "Topology Fidelity",
    description:
      "How well the shape of the dependency graph survived reconstruction. Higher is better; a low value means the causal structure itself is uncertain, not just the numbers on it.",
    implementationNote:
      "Structural-similarity proxy over the same amplitude pair: 1 − 2·sqrt(MSE), clamped to [0,1].",
  },
  /** Was `Strehl Ratio`. */
  peakRecovery: {
    label: "Peak Confidence Recovery",
    description:
      "Whether the most confident component in the fleet was recovered at full strength. Below 100% means the reconstruction flattened the strongest signal, so a genuinely healthy component may look degraded.",
    implementationNote:
      "Ratio of the reconstructed peak amplitude to the observed peak amplitude, energy-normalized (the Strehl ratio proxy).",
  },
} as const satisfies Record<string, Term>;

/** Status badge on the page header. */
export const STATUS_TERMS = {
  idle: {
    label: "Reconstruction Online",
    description: "The last reconstruction completed and is being displayed.",
    implementationNote: "No phase-retrieval job in flight.",
  },
  computing: {
    label: "Reconstructing State…",
    description:
      "Inverting the boundary telemetry into a 3D component-state field.",
    implementationNote: "Fienup HIO/ER schedule running (worker or main thread).",
  },
} as const satisfies Record<string, Term>;

/**
 * The four visualization modes.
 *
 * `value` strings are the wire contract consumed by `HologramVolume`'s
 * `displayMode` prop and the mode indices in `hologramMaterial.ts` — they are
 * deliberately left unchanged. Only what the engineer *reads* changes.
 */
export const VIEW_MODES = [
  {
    value: "phase_hue",
    label: "Confidence Field",
    description:
      "Component health and reconstruction confidence as colour across the fused state field.",
    implementationNote: "Phase-hue wavefront display.",
  },
  {
    value: "fringe_alarm",
    label: "Coverage Gaps",
    description:
      "Highlights regions where the reconstruction is unstable — the tell-tale of missing or contradictory telemetry.",
    implementationNote: "Fringe-aliasing alarm display.",
  },
  {
    value: "intensity_slice",
    label: "Time Window Slice",
    description:
      "A single depth slice through the fused state, for reading one moment of the incident in isolation.",
    implementationNote: "Angular-spectrum intensity slice.",
  },
  {
    value: "raw",
    label: "Raw Inversion",
    description:
      "The uncoloured reconstruction output, for when you want to judge the structure without the palette's help.",
    implementationNote: "Raw phase greyscale.",
  },
] as const satisfies ReadonlyArray<
  Term & { value: "phase_hue" | "fringe_alarm" | "intensity_slice" | "raw" }
>;

export type ViewModeValue = (typeof VIEW_MODES)[number]["value"];

/** Look up a view-mode label, tolerating a wire value we do not recognise. */
export function viewModeLabel(value: string): string {
  return VIEW_MODES.find((m) => m.value === value)?.label ?? value;
}

/**
 * The scene-view selector — a different axis from `VIEW_MODES` above.
 *
 * `VIEW_MODES` picks how the state field is *drawn*; these pick *what* is
 * drawn. Labels only: `value` is the `viewMode` state union and drives the
 * layout solver (`dagMode`, `linkDistance`) and which overlay renders.
 */
export const SCENE_VIEWS = [
  {
    value: "3d",
    label: "3D Reconstruction Volume",
    description:
      "The fused component-state field in three dimensions. Component height and depth encode state severity, not physical distance.",
    implementationNote: "Was labelled '3D Hologram Volume'. Force layout, dagMode 'none'.",
  },
  {
    value: "topology",
    label: "Causal Topology",
    description:
      "The dependency graph laid out as a directed acyclic graph, so causal direction reads top-to-bottom.",
    implementationNote: "Was labelled 'Causal DAG Topology'. Force layout, dagMode 'zout'.",
  },
  {
    value: "timeline",
    label: "Incident Timeline",
    description:
      "Component state over the incident's observation window, for reading when each component degraded.",
    implementationNote: "Was labelled 'Reality Rewind Timeline'.",
  },
] as const satisfies ReadonlyArray<
  Term & { value: "3d" | "topology" | "timeline" }
>;

/** The instrumentation facts panel — the constants that used to read as optics. */
export const INSTRUMENTATION_TERMS = {
  observationWindow: {
    label: "Observation Window",
    description:
      "The span of incident telemetry fused into this reconstruction. A short window means the causal ordering rests on little history.",
    implementationNote: "Replaces the fixed 532 nm wavelength caption; reads metadata.time_window_ns.",
  },
  samplingGrid: {
    label: "Fusion Grid",
    description:
      "Resolution of the lattice the component states were fused onto. Coarser grids merge nearby components.",
    implementationNote: "Replaces the fixed 8.0 µm pixel-pitch caption; reads the reconstruction grid size.",
  },
  solver: {
    label: "Inversion Method",
    description:
      "How boundary telemetry was inverted into the component-state field.",
    implementationNote:
      "Fienup Hybrid Input–Output / Error Reduction schedule, run in a Web Worker over the fused amplitude target.",
    value: "Fienup HIO/ER",
  },
  layout: {
    label: "Layout Solver",
    description: "Whether the force-directed graph layout has settled.",
    implementationNote: "d3-force-3d convergence state.",
  },
} as const satisfies Record<string, Term>;

/** Header copy. */
export const PAGE_TERMS = {
  title: "Holographic Reconstruction Engine",
  /** Was "Scalar Diffraction & Phase Retrieval". */
  subtitleWithIncident: (incidentId: string) =>
    `Incident: ${incidentId} • Boundary-to-Bulk State Inversion`,
  /** Was "Optical Wavefront & 3D Causal Graph Synthesis". */
  subtitleNoIncident: "Telemetry Fusion & 3D Causal Graph Synthesis",
  /** Was "Re-Synthesize". */
  recompute: "Reconstruct",
  /** Was "Hologram Reconstruction Telemetry". */
  telemetryCardTitle: "Reconstruction Confidence Telemetry",
  /** Was "ASM Propagation Slice". */
  sliceOverlayTitle: "Fused State Slice",
  /** Was the "Exposure" slider. It is a display gain, not a physical exposure. */
  displayGain: "Display Gain",
  /** Was "Optical Hologram Wavefront Volume Plane" in the scene comment. */
  volumeAriaLabel: "Reconstructed component-state field",
} as const;

/**
 * What this page publishes into the shell's incident context (the top bar).
 *
 * `title` and `pipelineStage` were previously "Holographic 3D Causal
 * Reconstruction" / "HOLOGRAPHIC_RECONSTRUCTION"; `pipelineStage` renders
 * verbatim as a pill in `TopContextBar`, so it is user-facing chrome, not an
 * internal key.
 */
export const SHELL_CONTEXT = {
  title: "Causal State Reconstruction",
  pipelineStage: "STATE_RECONSTRUCTION",
} as const;

/**
 * Evidence coverage as a percentage, from the boundary layers actually read.
 *
 * The page used to publish a hardcoded `evidenceCoverage: 0.94`, which drove a
 * progress ring in the top bar labelled "Evidence coverage: 0.94%" — a number
 * with no relationship to the incident on screen. This derives it from the
 * provenance record instead: the share of modelled telemetry dimensions that
 * reached the inversion.
 *
 * Returns 0 when provenance is unavailable, which reads as "unknown" in the
 * top bar rather than as a confident figure.
 */
export function evidenceCoveragePercent(
  observedLayerCount: number | undefined,
  totalLayers: number
): number {
  if (typeof observedLayerCount !== "number" || totalLayers <= 0) return 0;
  const clamped = Math.max(0, Math.min(observedLayerCount, totalLayers));
  return (clamped / totalLayers) * 100;
}

/**
 * Query-parameter names used for deep links between this page and the
 * downstream investigation tools.
 *
 * A single constant because the producer (this page) and the three consumers
 * (Ghost Lab, Patch Forge, Reality Rewind) must agree exactly; a typo on
 * either side is a silently dead link.
 */
export const DEEP_LINK_PARAM = "component";
/** Marks a visit as arriving from the reconstruction view, not the nav bar. */
export const DEEP_LINK_SOURCE_PARAM = "from";
export const DEEP_LINK_SOURCE_VALUE = "holographic-reconstruction";
/**
 * Which incident the linked component belongs to.
 *
 * Carried explicitly because the active incident otherwise lives only in
 * `localStorage`, which does not survive a link being opened in another tab,
 * pasted into a ticket, or bookmarked — the link would land on a different
 * incident's data and silently show the wrong component. Every downstream
 * page adopts this param via `useActiveIncident().setIncidentId`.
 */
export const DEEP_LINK_INCIDENT_PARAM = "incident";
/**
 * Optional, tool-specific selectors.
 *
 * These are only ever set where the target page genuinely keys on the id —
 * Ghost Lab on an experiment, Patch Forge on a patch candidate. There is no
 * equivalent for a component: no entity in the downstream tools carries a
 * component id, so `component` can only ever be a context hint there.
 */
export const DEEP_LINK_EXPERIMENT_PARAM = "experiment";
export const DEEP_LINK_PATCH_PARAM = "patch";

/**
 * Build the query string for a downstream tool.
 *
 * `componentId` is a `CausalNode.id` from this reconstruction's bulk graph.
 * `incidentId` is what makes the link durable; omitted only when the page has
 * no incident loaded, in which case the target falls back to its own
 * `localStorage` value.
 */
export function componentDeepLink(
  href: string,
  componentId: string | null,
  incidentId?: string | null
): string {
  const params = new URLSearchParams();
  if (componentId) params.set(DEEP_LINK_PARAM, componentId);
  if (incidentId) params.set(DEEP_LINK_INCIDENT_PARAM, incidentId);
  params.set(DEEP_LINK_SOURCE_PARAM, DEEP_LINK_SOURCE_VALUE);
  return `${href}?${params.toString()}`;
}

/** Everything a downstream page can learn from a reconstruction deep link. */
export interface DeepLink {
  /** A `CausalNode.id` from the reconstruction's bulk graph. */
  componentId: string | null;
  incidentId: string | null;
  experimentId: string | null;
  patchId: string | null;
  /** True when `from=holographic-reconstruction`. */
  arrivedFromReconstruction: boolean;
}

/**
 * Read a deep link out of a page's search params.
 *
 * Returns nulls rather than throwing, so a consumer page can call this
 * unconditionally — before it knows whether it is being deep-linked at all —
 * without a guard at every call site.
 */
export function readDeepLink(params: URLSearchParams | null): DeepLink {
  if (!params) {
    return {
      componentId: null,
      incidentId: null,
      experimentId: null,
      patchId: null,
      arrivedFromReconstruction: false,
    };
  }
  return {
    componentId: params.get(DEEP_LINK_PARAM),
    incidentId: params.get(DEEP_LINK_INCIDENT_PARAM),
    experimentId: params.get(DEEP_LINK_EXPERIMENT_PARAM),
    patchId: params.get(DEEP_LINK_PATCH_PARAM),
    arrivedFromReconstruction:
      params.get(DEEP_LINK_SOURCE_PARAM) === DEEP_LINK_SOURCE_VALUE,
  };
}

/** The three tools that can act on a specific component. */
export const COMPONENT_ACTIONS = [
  {
    href: "/ghost-lab",
    label: "Simulate in Ghost Lab",
    description: "Counterfactual intervention on this component",
  },
  {
    href: "/patch-forge",
    label: "Draft patch in Patch Forge",
    description: "Synthesize a remediation for this component",
  },
  {
    href: "/reality-rewind",
    label: "Replay in Reality Rewind",
    description: "Scrub this component's telemetry through the incident",
  },
] as const;
