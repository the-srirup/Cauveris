/**
 * Interprets a reconstruction payload's evidence provenance for display.
 *
 * The backend already does the hard part: it states where the evidence came
 * from and derives the warnings (see `cauveris/holographic/visualization.py`,
 * `build_provenance`). This module's only job is to turn that record into the
 * banner an engineer reads, and — critically — to handle the case where there
 * is no record at all.
 *
 * A payload with no `data_source` is *not* a trustworthy payload. It comes
 * from a backend older than this contract, or from the Next.js mock route.
 * Those render as "provenance unavailable", never as a clean bill of health.
 */

import type {
  DataSource,
  ProvenanceSeverity,
  ProvenanceWarning,
  VisualizationMetadata,
} from "../types";

/** Total boundary layers the reconstruction models — the denominator for coverage. */
export const TOTAL_BOUNDARY_LAYERS = 7;

export interface ProvenanceFact {
  label: string;
  value: string;
}

export interface ProvenanceSummary {
  /** `"unknown"` when the payload predates the provenance contract. */
  source: DataSource | "unknown";
  severity: ProvenanceSeverity;
  headline: string;
  detail: string;
  warnings: ProvenanceWarning[];
  /** Rendered as a small definition list under the headline. */
  facts: ProvenanceFact[];
  /** True when the graph on screen is fabricated. */
  isSynthetic: boolean;
}

/** Human-readable observation window from the backend's nanoseconds. */
export function formatObservationWindow(timeWindowNs: number | undefined): string {
  if (!timeWindowNs || !Number.isFinite(timeWindowNs) || timeWindowNs <= 0) {
    return "unknown";
  }
  const seconds = timeWindowNs / 1e9;
  if (seconds < 1) return `${(timeWindowNs / 1e6).toFixed(0)} ms`;
  if (seconds < 90) return `${seconds.toFixed(1)} s`;
  if (seconds < 5400) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

const HIGHEST_FIRST: Record<ProvenanceSeverity, number> = {
  critical: 3,
  warning: 2,
  info: 1,
};

function worstOf(warnings: ProvenanceWarning[]): ProvenanceSeverity {
  return warnings.reduce<ProvenanceSeverity>(
    (worst, w) => (HIGHEST_FIRST[w.severity] > HIGHEST_FIRST[worst] ? w.severity : worst),
    "info"
  );
}

export function summarizeProvenance(
  metadata: VisualizationMetadata | undefined
): ProvenanceSummary {
  const facts: ProvenanceFact[] = [];

  if (metadata) {
    facts.push({
      label: "Observation window",
      value: formatObservationWindow(metadata.time_window_ns),
    });
    if (typeof metadata.timeline_event_count === "number") {
      facts.push({
        label: "Timeline events",
        value: String(metadata.timeline_event_count),
      });
    }
    const observed = metadata.observed_boundary_layers?.length;
    if (typeof observed === "number") {
      facts.push({
        label: "Boundary layers read",
        value: `${observed} of ${TOTAL_BOUNDARY_LAYERS}`,
      });
    }
    if (metadata.bundle_path) {
      facts.push({ label: "Evidence bundle", value: metadata.bundle_path });
    }
  }

  // No contract at all — older backend or the local mock route. Fail loud
  // rather than assume the reconstruction is real.
  if (!metadata || metadata.data_source === undefined) {
    return {
      source: "unknown",
      severity: "warning",
      headline: "Evidence provenance unavailable",
      detail:
        "This payload does not declare where its evidence came from, so the graph on screen cannot be traced back to an incident bundle. Treat it as illustrative until the backend reports provenance.",
      warnings: [],
      facts,
      isSynthetic: false,
    };
  }

  const warnings = metadata.provenance_warnings ?? [];

  if (metadata.data_source === "synthetic_fallback") {
    const scenario = metadata.synthetic_incident_type
      ? ` The scenario shown is a fixed synthetic case (${metadata.synthetic_incident_type}${
          metadata.synthetic_seed != null ? `, seed ${metadata.synthetic_seed}` : ""
        }).`
      : "";
    const searched = metadata.bundle_search_paths?.length
      ? ` Searched: ${metadata.bundle_search_paths.join(", ")}.`
      : "";
    return {
      source: "synthetic_fallback",
      severity: "critical",
      headline: "No incident bundle — this reconstruction is synthetic",
      detail: `None of the expected evidence locations held a bundle for this incident, so Cauveris fabricated a scenario to keep the view renderable. It does not describe your system.${scenario}${searched}`,
      warnings,
      facts,
      isSynthetic: true,
    };
  }

  // Verified bundle. Warnings here are about how *complete* the evidence was,
  // not about whether it was real — say so explicitly so a sparse bundle is
  // not mistaken for the synthetic case.
  if (warnings.length === 0) {
    return {
      source: "verified_bundle",
      severity: "info",
      headline: "Reconstruction built from the incident bundle",
      detail:
        "Every component, edge and ambiguity region below was inverted from telemetry in the bundle.",
      warnings,
      facts,
      isSynthetic: false,
    };
  }

  const severity = worstOf(warnings);
  const count = warnings.length;
  return {
    source: "verified_bundle",
    severity,
    headline:
      severity === "critical"
        ? "Bundle found, but too sparse to reconstruct reliably"
        : `Bundle found — ${count} evidence gap${count === 1 ? "" : "s"} to read`,
    detail:
      "This reconstruction is built from your incident's evidence, but the bundle is missing telemetry the inversion depends on. The warnings below say what could not be concluded.",
    warnings,
    facts,
    isSynthetic: false,
  };
}
