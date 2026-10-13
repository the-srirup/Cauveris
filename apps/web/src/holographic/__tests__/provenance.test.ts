/**
 * Phase 1: sparse-bundle resilience.
 *
 * The defect this guards against is a quiet one: an incident whose evidence
 * bundle cannot be found used to be answered with a synthetic scenario and no
 * indication that anything was substituted. The graph looked plausible and was
 * fabricated.
 *
 * The backend now always states a `data_source` (see
 * `cauveris/holographic/visualization.py`, `build_provenance`). These tests
 * pin the frontend's half of that contract: every path through
 * `summarizeProvenance` either names a real bundle or says, in the banner's
 * own words, that the graph is not the engineer's system.
 */

import { describe, it, expect } from "vitest";
import {
  summarizeProvenance,
  formatObservationWindow,
  TOTAL_BOUNDARY_LAYERS,
} from "../domain/provenance";
import type {
  ProvenanceSeverity,
  ProvenanceWarning,
  VisualizationMetadata,
} from "../types";

/** A complete, verified payload; override only what a case is about. */
function metadata(overrides: Partial<VisualizationMetadata> = {}): VisualizationMetadata {
  return {
    overall_fidelity: 0.91,
    boundary_residual: 0.04,
    num_components: 12,
    num_ambiguity_regions: 2,
    time_window_ns: 90_000_000_000,
    generation_timestamp_ns: 1_700_000_000_000_000_000,
    data_source: "verified_bundle",
    ...overrides,
  };
}

function warning(severity: ProvenanceSeverity, code = "TEST"): ProvenanceWarning {
  return {
    code,
    severity,
    message: `${code} message`,
    impact: `${code} impact`,
    remediation: `${code} remediation`,
  };
}

describe("summarizeProvenance: no record at all", () => {
  it("treats a payload with no data_source as untraceable, not as healthy", () => {
    const summary = summarizeProvenance(metadata({ data_source: undefined }));
    expect(summary.source).toBe("unknown");
    expect(summary.severity).toBe("warning");
    expect(summary.headline).toMatch(/provenance unavailable/i);
    expect(summary.detail).toMatch(/cannot be traced back/i);
  });

  it("does the same when there is no metadata object at all", () => {
    const summary = summarizeProvenance(undefined);
    expect(summary.source).toBe("unknown");
    expect(summary.isSynthetic).toBe(false);
  });

  it("still reports whatever facts it could read", () => {
    const summary = summarizeProvenance(
      metadata({ data_source: undefined, time_window_ns: 5_000_000_000 })
    );
    expect(summary.facts).toContainEqual({
      label: "Observation window",
      value: "5.0 s",
    });
  });
});

describe("summarizeProvenance: synthetic fallback", () => {
  it("says outright that the graph is not the engineer's system", () => {
    const summary = summarizeProvenance(
      metadata({
        data_source: "synthetic_fallback",
        synthetic_incident_type: "cascading_timeout",
        synthetic_seed: 42,
        bundle_search_paths: ["/data/incidents/CAU-0001", "/mnt/evidence/CAU-0001"],
      })
    );
    expect(summary.severity).toBe("critical");
    expect(summary.isSynthetic).toBe(true);
    expect(summary.headline).toMatch(/synthetic/i);
    expect(summary.detail).toMatch(/does not describe your system/i);
    expect(summary.detail).toMatch(/cascading_timeout/);
    expect(summary.detail).toMatch(/seed 42/);
  });

  it("names every location that was probed, so the search is auditable", () => {
    const summary = summarizeProvenance(
      metadata({
        data_source: "synthetic_fallback",
        bundle_search_paths: ["/data/incidents/CAU-0001", "/mnt/evidence/CAU-0001"],
      })
    );
    expect(summary.detail).toContain("/data/incidents/CAU-0001");
    expect(summary.detail).toContain("/mnt/evidence/CAU-0001");
    expect(summary.detail).toMatch(/Searched:/);
  });
});

describe("summarizeProvenance: verified bundle", () => {
  it("reads as a clean bill of health only when there are no warnings", () => {
    const summary = summarizeProvenance(metadata({ provenance_warnings: [] }));
    expect(summary.source).toBe("verified_bundle");
    expect(summary.severity).toBe("info");
    expect(summary.isSynthetic).toBe(false);
    expect(summary.headline).toMatch(/built from the incident bundle/i);
  });

  it("a sparse bundle is never reported as synthetic", () => {
    // The whole point of the split: sparse evidence is a *quality* problem
    // with real evidence, not a substitution. Conflating them was the bug.
    const summary = summarizeProvenance(
      metadata({
        provenance_warnings: [warning("warning", "BOUNDARY_LAYERS_MISSING")],
      })
    );
    expect(summary.isSynthetic).toBe(false);
    expect(summary.source).toBe("verified_bundle");
    expect(summary.detail).toMatch(/built from your incident's evidence/i);
  });

  it("escalates the banner to the worst warning present", () => {
    const summary = summarizeProvenance(
      metadata({
        provenance_warnings: [
          warning("info", "BOUNDARY_LAYERS_UNDECLARED"),
          warning("warning", "SPARSE_TIMELINE"),
          warning("critical", "PROVENANCE_NOT_RECORDED"),
        ],
      })
    );
    expect(summary.severity).toBe("critical");
    expect(summary.headline).toMatch(/too sparse to reconstruct reliably/i);
  });

  it("counts gaps in the headline, and pluralises honestly", () => {
    const one = summarizeProvenance(
      metadata({ provenance_warnings: [warning("warning")] })
    );
    expect(one.headline).toMatch(/1 evidence gap to read/);

    const three = summarizeProvenance(
      metadata({ provenance_warnings: [warning("warning"), warning("warning"), warning("info")] })
    );
    expect(three.headline).toMatch(/3 evidence gaps to read/);
  });

  it("passes backend warnings through verbatim rather than re-summarising them", () => {
    // The backend owns the wording ("what you cannot conclude", "what would
    // fix it"); the frontend must not paraphrase a safety statement.
    const warnings = [warning("critical", "PROVENANCE_NOT_RECORDED")];
    const summary = summarizeProvenance(metadata({ provenance_warnings: warnings }));
    expect(summary.warnings).toEqual(warnings);
  });

  it("survives a payload that omits the warnings array entirely", () => {
    const summary = summarizeProvenance(metadata({ provenance_warnings: undefined }));
    expect(summary.warnings).toEqual([]);
    expect(summary.severity).toBe("info");
  });
});

describe("summarizeProvenance: facts", () => {
  it("reports boundary-layer coverage against the modelled total", () => {
    const summary = summarizeProvenance(
      metadata({ observed_boundary_layers: ["application_log", "metrics_export"] })
    );
    expect(summary.facts).toContainEqual({
      label: "Boundary layers read",
      value: `2 of ${TOTAL_BOUNDARY_LAYERS}`,
    });
  });

  it("omits a fact it has no data for instead of printing a guess", () => {
    const summary = summarizeProvenance(
      metadata({ observed_boundary_layers: undefined, bundle_path: undefined })
    );
    const labels = summary.facts.map((f) => f.label);
    expect(labels).not.toContain("Boundary layers read");
    expect(labels).not.toContain("Evidence bundle");
  });

  it("reports the timeline event count when present, including zero", () => {
    const summary = summarizeProvenance(metadata({ timeline_event_count: 0 }));
    expect(summary.facts).toContainEqual({ label: "Timeline events", value: "0" });
  });
});

describe("formatObservationWindow", () => {
  it("scales the unit to the window", () => {
    expect(formatObservationWindow(250_000_000)).toBe("250 ms");
    expect(formatObservationWindow(5_000_000_000)).toBe("5.0 s");
    expect(formatObservationWindow(300_000_000_000)).toBe("5.0 min");
    expect(formatObservationWindow(7_200_000_000_000)).toBe("2.0 h");
  });

  it("says 'unknown' rather than inventing a window", () => {
    expect(formatObservationWindow(undefined)).toBe("unknown");
    expect(formatObservationWindow(0)).toBe("unknown");
    expect(formatObservationWindow(-1)).toBe("unknown");
    expect(formatObservationWindow(Number.NaN)).toBe("unknown");
  });
});
